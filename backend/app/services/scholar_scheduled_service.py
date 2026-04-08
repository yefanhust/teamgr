"""Scholar scheduled questions service — run scholar queries on a cron schedule."""

import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_DATA_DIR = os.environ.get("TEAMGR_DATA_DIR", "/app/data")
_QUEUE_DIR = os.path.join(_DATA_DIR, "scholar-queue")
_STREAM_DIR = os.path.join(_DATA_DIR, "scholar-stream")

_CN_TZ = timezone(timedelta(hours=8))

# Error markers from watcher-side failures (scholar-watcher.sh writes these)
_FAILURE_MARKERS = ["调用失败", "执行超时", "未获取到回答"]


def _is_failed_answer(answer: str) -> bool:
    """Check if the answer indicates a failure (backend or watcher-side errors)."""
    if answer.startswith("["):
        return True
    return any(m in answer for m in _FAILURE_MARKERS)


# Ensure dirs exist
for _d in (_QUEUE_DIR, _STREAM_DIR):
    os.makedirs(_d, exist_ok=True)

# Track active query_id per question_id for progress polling
_active_queries: dict[int, str] = {}  # question_id -> query_id


def _gen_id() -> str:
    return uuid.uuid4().hex[:12]


def get_execution_progress(question_id: int) -> dict:
    """Read the stream file for an active query and extract progress events."""
    query_id = _active_queries.get(question_id)
    if not query_id:
        return {"running": False}

    stream_file = os.path.join(_STREAM_DIR, f"{query_id}.jsonl")
    done_file = os.path.join(_STREAM_DIR, f"{query_id}.done")

    if not os.path.exists(stream_file):
        return {"running": True, "query_id": query_id, "events": [], "stage": "等待处理..."}

    events = []
    last_stage = "执行中..."
    try:
        with open(stream_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue

                etype = event.get("type", "")
                if etype == "assistant":
                    msg = event.get("message", {})
                    if isinstance(msg, str):
                        try:
                            msg = json.loads(msg)
                        except (json.JSONDecodeError, ValueError):
                            continue
                    for block in msg.get("content", []):
                        bt = block.get("type", "")
                        if bt == "tool_use":
                            tool = block.get("name", "")
                            inp = block.get("input", {})
                            if tool == "WebSearch":
                                query = inp.get("query", "")
                                events.append({"type": "search", "query": query})
                                last_stage = f"搜索: {query}"
                            elif tool == "WebFetch":
                                url = inp.get("url", "")
                                events.append({"type": "fetch", "url": url})
                                last_stage = f"读取: {url[:60]}"
                        elif bt == "text":
                            text = block.get("text", "")
                            if text and len(text) > 10:
                                last_stage = "正在撰写内容..."
                elif etype == "result":
                    last_stage = "完成"
    except OSError:
        pass

    is_done = os.path.exists(done_file)
    if is_done:
        _active_queries.pop(question_id, None)

    return {
        "running": not is_done,
        "query_id": query_id,
        "events": events[-15:],  # last 15 events
        "stage": last_stage,
        "done": is_done,
    }


def _render_prompt(template: str, schedule_type: str) -> str:
    """Replace template variables in prompt."""
    now = datetime.now(_CN_TZ)
    replacements = {
        "{date}": now.strftime("%Y年%m月%d日"),
        "{week_label}": f"{now.year}年第{now.isocalendar()[1]}周",
        "{month_label}": now.strftime("%Y年%m月"),
    }
    result = template
    for key, value in replacements.items():
        result = result.replace(key, value)
    return result


def _get_period_label(schedule_type: str) -> str:
    """Generate a period label for dedup."""
    now = datetime.now(_CN_TZ)
    if schedule_type == "daily":
        return now.strftime("%Y-%m-%d")
    elif schedule_type == "weekly":
        iso = now.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    elif schedule_type == "monthly":
        return now.strftime("%Y-%m")
    return now.strftime("%Y-%m-%d")


def _extract_answer_from_stream(stream_file: str) -> str:
    """Extract the final text answer from a stream-json file.

    Uses the 'result' event (authoritative final output) when available.
    Falls back to the LAST assistant text block (multi-turn conversations
    produce multiple assistant events; only the last one has the final answer).
    """
    if not os.path.exists(stream_file):
        return ""

    result_text = ""
    last_assistant_texts = []
    try:
        with open(stream_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue

                etype = event.get("type", "")

                if etype == "assistant":
                    msg = event.get("message", {})
                    if isinstance(msg, str):
                        try:
                            msg = json.loads(msg)
                        except (json.JSONDecodeError, ValueError):
                            continue
                    texts = []
                    for block in msg.get("content", []):
                        if block.get("type") == "text":
                            text = block.get("text", "")
                            if text:
                                texts.append(text)
                    if texts:
                        # Each new assistant event replaces — we only want the last one
                        last_assistant_texts = texts

                elif etype == "result":
                    result_text = event.get("result", "")
    except OSError as e:
        logger.error(f"Failed to read stream file: {e}")

    # Prefer result event (clean final answer); fall back to last assistant block
    if result_text:
        return result_text
    if last_assistant_texts:
        return "".join(last_assistant_texts)
    return ""


def run_single_scholar_query(prompt: str, timeout: int = 1200, question_id: int = None) -> tuple[str, float]:
    """Write a signal file and poll for completion. Returns (answer, duration_seconds)."""
    query_id = f"sched_{_gen_id()}"

    # Track active query for progress polling
    if question_id is not None:
        _active_queries[question_id] = query_id

    signal = {
        "query_id": query_id,
        "conversation_id": f"sched_{_gen_id()}",
        "session_id": "",
        "prompt": prompt,
        "context": "",
        "timestamp": int(datetime.now().timestamp()),
    }

    signal_path = os.path.join(_QUEUE_DIR, f"{query_id}.json")
    with open(signal_path, "w", encoding="utf-8") as f:
        json.dump(signal, f, ensure_ascii=False)

    logger.info(f"Scholar scheduled query signal written: {query_id}")

    # Poll for completion
    done_file = os.path.join(_STREAM_DIR, f"{query_id}.done")
    stream_file = os.path.join(_STREAM_DIR, f"{query_id}.jsonl")
    start = time.time()

    while time.time() - start < timeout:
        if os.path.exists(done_file):
            break
        time.sleep(0.5)

    duration = time.time() - start

    if not os.path.exists(done_file):
        logger.error(f"Scholar scheduled query timed out: {query_id}")
        return f"[执行超时 ({timeout}s)]", duration

    answer = _extract_answer_from_stream(stream_file)
    if not answer:
        answer = "[未获取到回答]"

    logger.info(f"Scholar scheduled query completed: {query_id} ({duration:.1f}s, {len(answer)} chars)")

    # Clean up tracking and stream files
    if question_id is not None:
        _active_queries.pop(question_id, None)
    try:
        os.remove(done_file)
        os.remove(stream_file)
    except OSError:
        pass

    return answer, duration


def _build_context_from_dependency(depends_on_id: int, context_days: int) -> str:
    """Fetch recent results from a dependency question and format as context."""
    from app.database import SessionLocal
    from app.models.scholar import ScholarScheduledResult, ScholarScheduledQuestion

    db = SessionLocal()
    try:
        dep_question = db.query(ScholarScheduledQuestion).filter(
            ScholarScheduledQuestion.id == depends_on_id
        ).first()
        if not dep_question:
            return ""

        cutoff = datetime.utcnow() - timedelta(days=context_days)
        results = (
            db.query(ScholarScheduledResult)
            .filter(
                ScholarScheduledResult.question_id == depends_on_id,
                ScholarScheduledResult.status == "success",
                ScholarScheduledResult.generated_at >= cutoff,
            )
            .order_by(ScholarScheduledResult.generated_at.asc())
            .all()
        )

        if not results:
            return ""

        parts = []
        for r in results:
            parts.append(f"### {r.period_label}\n{r.answer}")

        context = f"以下是「{dep_question.title}」最近{context_days}天的结果：\n\n" + "\n\n---\n\n".join(parts)
        # Limit context size
        if len(context) > 100000:
            context = context[:100000] + "\n\n[... 内容过长，已截断 ...]"
        return context
    finally:
        db.close()


_SCHOLAR_JOB_PREFIX = "scholar_q_"
_SCHOLAR_RECOVERY_PREFIX = "scholar_recovery_"


def refresh_scholar_jobs(scheduler):
    """Register one APScheduler job per enabled scheduled question, using each question's own cron time."""
    from app.database import SessionLocal
    from app.models.scholar import ScholarScheduledQuestion

    if scheduler is None:
        return

    # Remove all existing scholar question jobs
    for job in scheduler.get_jobs():
        if job.id.startswith(_SCHOLAR_JOB_PREFIX):
            scheduler.remove_job(job.id)

    db = SessionLocal()
    try:
        questions = db.query(ScholarScheduledQuestion).filter(
            ScholarScheduledQuestion.enabled == True,
        ).all()

        for q in questions:
            job_id = f"{_SCHOLAR_JOB_PREFIX}{q.id}"
            trigger_kwargs = {
                "hour": q.cron_hour,
                "minute": q.cron_minute,
            }
            if q.schedule_type == "weekly":
                trigger_kwargs["day_of_week"] = q.day_of_week or "mon"
            elif q.schedule_type == "monthly":
                trigger_kwargs["day"] = q.day_of_month or 1

            # Create a closure that captures q.id
            def make_job(qid):
                return lambda: _run_single_question_cron(qid)

            scheduler.add_job(
                make_job(q.id),
                "cron",
                id=job_id,
                replace_existing=True,
                **trigger_kwargs,
            )
            logger.info(
                f"Scholar job registered: '{q.title}' ({q.schedule_type}) "
                f"at {q.cron_hour:02d}:{q.cron_minute:02d} [job={job_id}]"
            )

        logger.info(f"Scholar scheduler refreshed: {len(questions)} job(s)")
    finally:
        db.close()


def check_missed_executions(scheduler):
    """On startup, detect scheduled questions that missed their execution window
    (e.g. due to server restart) and schedule immediate recovery runs.

    Checks both today's and yesterday's period for daily questions, since a server
    restart after the scheduled time would leave the previous day's result missing.
    """
    from app.database import SessionLocal
    from app.models.scholar import ScholarScheduledQuestion, ScholarScheduledResult

    if scheduler is None:
        return

    now = datetime.now(_CN_TZ)
    db = SessionLocal()
    try:
        questions = db.query(ScholarScheduledQuestion).filter(
            ScholarScheduledQuestion.enabled == True,
        ).all()

        recovery_count = 0
        for q in questions:
            # Build list of period labels to check
            periods_to_check = []

            if q.schedule_type == "daily":
                today_label = now.strftime("%Y-%m-%d")
                yesterday_label = (now - timedelta(days=1)).strftime("%Y-%m-%d")
                periods_to_check.append(yesterday_label)
                scheduled_time = now.replace(
                    hour=q.cron_hour, minute=q.cron_minute, second=0, microsecond=0
                )
                if now >= scheduled_time:
                    periods_to_check.append(today_label)
            elif q.schedule_type == "weekly":
                # Check current week
                iso = now.isocalendar()
                periods_to_check.append(f"{iso[0]}-W{iso[1]:02d}")
            elif q.schedule_type == "monthly":
                # Check current month
                periods_to_check.append(now.strftime("%Y-%m"))

            for period_label in periods_to_check:
                existing = (
                    db.query(ScholarScheduledResult)
                    .filter(
                        ScholarScheduledResult.question_id == q.id,
                        ScholarScheduledResult.period_label == period_label,
                        ScholarScheduledResult.status == "success",
                    )
                    .first()
                )
                if existing:
                    continue  # Already has result

                # Schedule recovery run with staggered delays to avoid overload
                delay_seconds = 60 + recovery_count * 300  # 1min, 6min, 11min, ...
                run_at = datetime.now() + timedelta(seconds=delay_seconds)

                def make_recovery(qid):
                    return lambda: _run_single_question_cron(qid)

                job_id = f"{_SCHOLAR_RECOVERY_PREFIX}{q.id}_{period_label}"
                scheduler.add_job(
                    make_recovery(q.id),
                    "date",
                    run_date=run_at,
                    id=job_id,
                    replace_existing=True,
                )
                recovery_count += 1
                logger.info(
                    f"Missed execution detected for '{q.title}' [{period_label}], "
                    f"recovery scheduled in {delay_seconds}s [job={job_id}]"
                )

        if recovery_count:
            logger.info(f"Scholar startup recovery: {recovery_count} missed execution(s) scheduled")
        else:
            logger.info("Scholar startup recovery: no missed executions detected")

        # Clean up orphaned stream files (older than 24h)
        _cleanup_orphaned_stream_files()

    except Exception as e:
        logger.error(f"Failed to check missed executions: {e}")
    finally:
        db.close()


def _cleanup_orphaned_stream_files():
    """Remove old sched_*.done and sched_*.jsonl files left by interrupted runs."""
    cutoff = time.time() - 86400  # 24 hours
    try:
        for fname in os.listdir(_STREAM_DIR):
            if not fname.startswith("sched_"):
                continue
            fpath = os.path.join(_STREAM_DIR, fname)
            try:
                if os.path.getmtime(fpath) < cutoff:
                    os.remove(fpath)
                    logger.info(f"Cleaned up orphaned stream file: {fname}")
            except OSError:
                pass
    except OSError:
        pass


def _run_single_question_cron(question_id: int):
    """APScheduler entry point for a single question. Runs the question and saves result."""
    from app.database import SessionLocal
    from app.models.scholar import ScholarScheduledQuestion, ScholarScheduledResult

    db = SessionLocal()
    try:
        q = db.query(ScholarScheduledQuestion).filter(
            ScholarScheduledQuestion.id == question_id,
            ScholarScheduledQuestion.enabled == True,
        ).first()
        if not q:
            return

        logger.info(f"Cron executing: '{q.title}' (id={q.id})")
        period_label = _get_period_label(q.schedule_type)

        try:
            rendered_prompt = _render_prompt(q.prompt, q.schedule_type)
            if q.depends_on_id:
                context = _build_context_from_dependency(q.depends_on_id, q.context_days)
                if context:
                    rendered_prompt = context + "\n\n---\n\n" + rendered_prompt

            answer, duration = run_single_scholar_query(rendered_prompt, question_id=question_id)
            status = "failed" if _is_failed_answer(answer) else "success"

            # Remove old results for this period (cron always gets latest)
            old_count = (
                db.query(ScholarScheduledResult)
                .filter(
                    ScholarScheduledResult.question_id == q.id,
                    ScholarScheduledResult.period_label == period_label,
                )
                .delete()
            )
            if old_count:
                logger.info(f"Replaced {old_count} old result(s) for '{q.title}' [{period_label}]")

            result = ScholarScheduledResult(
                question_id=q.id,
                question_snapshot=rendered_prompt[:500],
                answer=answer,
                period_label=period_label,
                schedule_type=q.schedule_type,
                status=status,
                model_name="claude-code-cli",
                generated_at=datetime.utcnow(),
                duration_seconds=duration,
            )
            db.add(result)
            db.commit()
            logger.info(f"Cron result saved: '{q.title}' [{period_label}]")

            # Pre-generate TTS audio so it's ready when users want to listen
            if status == "success":
                from app.services.tts_service import generate_tts_cache_sync
                tts_path = generate_tts_cache_sync(answer)
                if tts_path:
                    logger.info(f"TTS pre-generated for '{q.title}' [{period_label}]")

        except Exception as e:
            logger.error(f"Cron execution failed for '{q.title}': {e}")
            db.rollback()
    finally:
        db.close()


def run_scholar_scheduled_job(schedule_type: str):
    """APScheduler entry point (legacy). Run all enabled questions of a given schedule_type."""
    from app.database import SessionLocal
    from app.models.scholar import ScholarScheduledQuestion, ScholarScheduledResult

    logger.info(f"Starting scholar scheduled job: {schedule_type}")

    db = SessionLocal()
    try:
        questions = (
            db.query(ScholarScheduledQuestion)
            .filter(
                ScholarScheduledQuestion.schedule_type == schedule_type,
                ScholarScheduledQuestion.enabled == True,
            )
            .order_by(ScholarScheduledQuestion.id)
            .all()
        )

        if not questions:
            logger.info(f"No enabled {schedule_type} scholar questions. Skipping.")
            return

        logger.info(f"Found {len(questions)} {schedule_type} scholar question(s)")

        period_label = _get_period_label(schedule_type)

        for q in questions:
            try:
                # Build prompt
                rendered_prompt = _render_prompt(q.prompt, schedule_type)

                # Inject dependency context
                if q.depends_on_id:
                    context = _build_context_from_dependency(q.depends_on_id, q.context_days)
                    if context:
                        rendered_prompt = context + "\n\n---\n\n" + rendered_prompt

                # Execute
                answer, duration = run_single_scholar_query(rendered_prompt)
                status = "failed" if _is_failed_answer(answer) else "success"

                # Remove old results for this period (cron always gets latest)
                old_count = (
                    db.query(ScholarScheduledResult)
                    .filter(
                        ScholarScheduledResult.question_id == q.id,
                        ScholarScheduledResult.period_label == period_label,
                    )
                    .delete()
                )
                if old_count:
                    logger.info(f"Replaced {old_count} old result(s) for '{q.title}' [{period_label}]")

                result = ScholarScheduledResult(
                    question_id=q.id,
                    question_snapshot=rendered_prompt[:500],
                    answer=answer,
                    period_label=period_label,
                    schedule_type=schedule_type,
                    status=status,
                    model_name="claude-code-cli",
                    generated_at=datetime.utcnow(),
                    duration_seconds=duration,
                )
                db.add(result)
                db.commit()
                logger.info(f"Scholar scheduled result saved: '{q.title}' [{period_label}]")

                # Pre-generate TTS audio so it's ready when users want to listen
                if status == "success":
                    from app.services.tts_service import generate_tts_cache_sync
                    tts_path = generate_tts_cache_sync(answer)
                    if tts_path:
                        logger.info(f"TTS pre-generated for '{q.title}' [{period_label}]")

            except Exception as e:
                logger.error(f"Scholar scheduled query failed for '{q.title}': {e}")
                db.rollback()
                # Save failed result
                try:
                    result = ScholarScheduledResult(
                        question_id=q.id,
                        question_snapshot=q.prompt[:500],
                        answer=f"[执行失败: {e}]",
                        period_label=period_label,
                        schedule_type=schedule_type,
                        status="failed",
                        model_name="claude-code-cli",
                        generated_at=datetime.utcnow(),
                    )
                    db.add(result)
                    db.commit()
                except Exception:
                    db.rollback()

    finally:
        db.close()

    logger.info(f"Scholar scheduled job finished: {schedule_type}")


def run_single_question_now(question_id: int, force: bool = False) -> dict:
    """Manually trigger a single scheduled question. Returns the result dict."""
    from app.database import SessionLocal
    from app.models.scholar import ScholarScheduledQuestion, ScholarScheduledResult

    db = SessionLocal()
    try:
        q = db.query(ScholarScheduledQuestion).filter(
            ScholarScheduledQuestion.id == question_id
        ).first()
        if not q:
            return {"error": "问题不存在"}

        period_label = _get_period_label(q.schedule_type)

        # Check dedup unless force
        if not force:
            existing = (
                db.query(ScholarScheduledResult)
                .filter(
                    ScholarScheduledResult.question_id == q.id,
                    ScholarScheduledResult.period_label == period_label,
                    ScholarScheduledResult.status == "success",
                )
                .first()
            )
            if existing:
                return {
                    "skipped": True,
                    "message": f"已有 {period_label} 的结果，使用 force=true 强制重新执行",
                    "result_id": existing.id,
                }

        # Build prompt
        rendered_prompt = _render_prompt(q.prompt, q.schedule_type)
        if q.depends_on_id:
            context = _build_context_from_dependency(q.depends_on_id, q.context_days)
            if context:
                rendered_prompt = context + "\n\n---\n\n" + rendered_prompt

        answer, duration = run_single_scholar_query(rendered_prompt, question_id=question_id)
        status = "failed" if _is_failed_answer(answer) else "success"

        # If forcing, delete old result for same period
        if force:
            db.query(ScholarScheduledResult).filter(
                ScholarScheduledResult.question_id == q.id,
                ScholarScheduledResult.period_label == period_label,
            ).delete()

        result = ScholarScheduledResult(
            question_id=q.id,
            question_snapshot=rendered_prompt[:500],
            answer=answer,
            period_label=period_label,
            schedule_type=q.schedule_type,
            status=status,
            model_name="claude-code-cli",
            generated_at=datetime.utcnow(),
            duration_seconds=duration,
        )
        db.add(result)
        db.commit()
        db.refresh(result)

        # Pre-generate TTS audio so it's ready when users want to listen
        if status == "success":
            from app.services.tts_service import generate_tts_cache_sync
            tts_path = generate_tts_cache_sync(answer)
            if tts_path:
                logger.info(f"TTS pre-generated for '{q.title}' [{period_label}]")

        return {
            "result_id": result.id,
            "status": result.status,
            "period_label": result.period_label,
            "duration_seconds": result.duration_seconds,
            "answer_length": len(result.answer),
        }
    finally:
        db.close()


def seed_default_scheduled_questions():
    """Seed default scheduled questions if none exist."""
    from app.database import SessionLocal
    from app.models.scholar import ScholarScheduledQuestion

    db = SessionLocal()
    try:
        if db.query(ScholarScheduledQuestion).count() > 0:
            return

        finance_daily = ScholarScheduledQuestion(
            title="每日财经要闻",
            prompt="请搜索并整理今天（{date}）最重要的10个财经新闻，每条包含：\n1. 标题\n2. 核心内容摘要（2-3句话）\n3. 影响分析（对市场/经济的潜在影响）\n\n最后附上「今日市场速览」表格，列出主要指数/商品的收盘价和涨跌幅，涨跌幅用+/-前缀表示。\n\n**搜索要求：**\n- 必须同时搜索中文和英文信息源，确保国内外覆盖均衡\n- 国际来源：Reuters, Bloomberg, Financial Times, WSJ, CNBC 等\n- 国内来源：财新、第一财经、证券时报、经济观察报等\n- 10条新闻中，国际新闻不少于4条\n- 请用中文撰写所有内容",
            schedule_type="daily",
            cron_hour=6,
            cron_minute=0,
            enabled=False,
        )
        db.add(finance_daily)
        db.flush()

        tech_daily = ScholarScheduledQuestion(
            title="每日科技进展",
            prompt="请搜索并整理今天（{date}）最重要的10个科技进展，每条包含：\n1. 标题\n2. 核心内容摘要（2-3句话）\n3. 意义分析（技术突破点和行业影响）\n\n**搜索要求：**\n- 必须同时搜索中文和英文信息源，确保国内外覆盖均衡\n- 国际来源：TechCrunch, Ars Technica, The Verge, Wired, MIT Technology Review, Nature, Science 等\n- 国内来源：36氪、量子位、机器之心、IT之家等\n- 涵盖 AI、半导体、新能源、航天、生物科技、量子计算等领域\n- 10条新闻中，国际科技进展不少于4条\n- 请用中文撰写所有内容",
            schedule_type="daily",
            cron_hour=6,
            cron_minute=30,
            enabled=False,
        )
        db.add(tech_daily)
        db.flush()

        db.add(ScholarScheduledQuestion(
            title="每周经济趋势",
            prompt="基于过去一周的每日财经新闻数据，请分析{week_label}的经济趋势：\n1. 本周最重要的3-5个经济主题\n2. 各主题的发展脉络和趋势判断\n3. 对下周的展望和需要关注的风险点\n\n请结合宏观经济指标和政策动向给出深入分析。",
            schedule_type="weekly",
            cron_hour=7,
            cron_minute=0,
            day_of_week="mon",
            depends_on_id=finance_daily.id,
            context_days=7,
            enabled=False,
        ))

        db.add(ScholarScheduledQuestion(
            title="每周科技趋势",
            prompt="基于过去一周的每日科技进展数据，请分析{week_label}的科技发展趋势：\n1. 本周最重要的3-5个科技主题\n2. 各主题的技术突破和产业影响\n3. 值得持续关注的技术方向\n\n请给出有深度的趋势判断。",
            schedule_type="weekly",
            cron_hour=7,
            cron_minute=30,
            day_of_week="mon",
            depends_on_id=tech_daily.id,
            context_days=7,
            enabled=False,
        ))

        db.add(ScholarScheduledQuestion(
            title="每月经济趋势",
            prompt="基于过去一个月的每日财经新闻数据，请总结{month_label}的经济趋势：\n1. 本月最重要的经济事件和政策变化\n2. 主要经济指标的变化趋势\n3. 行业热点和投资方向变化\n4. 对下月经济走势的预判\n\n请给出系统性的月度经济分析报告。",
            schedule_type="monthly",
            cron_hour=8,
            cron_minute=0,
            day_of_month=1,
            depends_on_id=finance_daily.id,
            context_days=30,
            enabled=False,
        ))

        db.add(ScholarScheduledQuestion(
            title="每月科技趋势",
            prompt="基于过去一个月的每日科技进展数据，请总结{month_label}的科技发展趋势：\n1. 本月最重大的技术突破\n2. 各技术领域的发展动态\n3. 产业格局变化和新兴方向\n4. 对未来技术发展的预判\n\n请给出系统性的月度科技分析报告。",
            schedule_type="monthly",
            cron_hour=8,
            cron_minute=30,
            day_of_month=1,
            depends_on_id=tech_daily.id,
            context_days=30,
            enabled=False,
        ))

        db.commit()
        logger.info("Seeded 6 default scholar scheduled questions")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to seed scheduled questions: {e}")
    finally:
        db.close()
