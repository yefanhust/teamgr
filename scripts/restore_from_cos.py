#!/usr/bin/env python3
"""
Restore TeamGr backup from Tencent Cloud COS.

Usage:
    pip install cos-python-sdk-v5 cryptography
    python scripts/restore_from_cos.py \
        --secret-id YOUR_COS_SECRET_ID \
        --secret-key YOUR_COS_SECRET_KEY \
        --region ap-singapore \
        --bucket taco-sg-1251783334 \
        --password YOUR_BACKUP_PASSWORD

    # Restore a specific timestamp version:
    python scripts/restore_from_cos.py ... --timestamp 20260315_043000

    # Restore legacy unencrypted .db backup:
    python scripts/restore_from_cos.py ... --legacy
"""

import argparse
import os
import sys
import tarfile
import tempfile


def decrypt_file(src_path: str, dst_path: str, password: str):
    """Decrypt AES-256-GCM encrypted file."""
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    with open(src_path, "rb") as f:
        salt = f.read(16)
        nonce = f.read(12)
        ciphertext = f.read()

    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480_000)
    key = kdf.derive(password.encode("utf-8"))
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)

    with open(dst_path, "wb") as f:
        f.write(plaintext)


def main():
    parser = argparse.ArgumentParser(description="Restore TeamGr backup from COS")
    parser.add_argument("--secret-id", required=True, help="COS SecretId")
    parser.add_argument("--secret-key", required=True, help="COS SecretKey")
    parser.add_argument("--region", required=True, help="COS region (e.g. ap-singapore)")
    parser.add_argument("--bucket", required=True, help="COS bucket name")
    parser.add_argument("--prefix", default="teamgr/", help="COS key prefix (default: teamgr/)")
    parser.add_argument("--password", default="", help="Backup encryption password")
    parser.add_argument("--timestamp", default="", help="Specific backup timestamp (e.g. 20260315_043000)")
    parser.add_argument("--legacy", action="store_true", help="Restore legacy .db format (unencrypted)")
    parser.add_argument("--target", default=".", help="Project root directory (default: current dir)")
    args = parser.parse_args()

    # Validate target directory
    target = os.path.abspath(args.target)
    if not os.path.isdir(target):
        print(f"Error: target directory '{target}' does not exist")
        sys.exit(1)

    # Check for existing data
    data_dir = os.path.join(target, "data")
    config_dir = os.path.join(target, "config")
    db_path = os.path.join(data_dir, "teamgr.db")

    if os.path.exists(db_path):
        response = input(f"WARNING: {db_path} already exists. Overwrite? [y/N] ")
        if response.lower() != "y":
            print("Aborted.")
            sys.exit(0)

    # Initialize COS client
    try:
        from qcloud_cos import CosConfig, CosS3Client
    except ImportError:
        print("Error: cos-python-sdk-v5 not installed. Run: pip install cos-python-sdk-v5")
        sys.exit(1)

    cos_config = CosConfig(
        Region=args.region,
        SecretId=args.secret_id,
        SecretKey=args.secret_key,
    )
    client = CosS3Client(cos_config)

    # Determine COS key
    if args.legacy:
        if args.timestamp:
            cos_key = f"{args.prefix}teamgr_{args.timestamp}.db"
        else:
            cos_key = f"{args.prefix}latest.db"
    else:
        if args.timestamp:
            cos_key = f"{args.prefix}teamgr_{args.timestamp}.tar.gz.enc"
        else:
            cos_key = f"{args.prefix}latest.tar.gz.enc"

    print(f"Downloading: {cos_key} ...")

    with tempfile.TemporaryDirectory(prefix="teamgr_restore_") as tmp_dir:
        local_file = os.path.join(tmp_dir, "downloaded")

        try:
            client.download_file(
                Bucket=args.bucket,
                Key=cos_key,
                DestFilePath=local_file,
            )
        except Exception as e:
            print(f"Error downloading from COS: {e}")
            sys.exit(1)

        file_size = os.path.getsize(local_file)
        print(f"Downloaded: {file_size / 1024:.1f} KB")

        if args.legacy:
            # Legacy mode: just a .db file
            os.makedirs(data_dir, exist_ok=True)
            import shutil
            shutil.copy2(local_file, db_path)
            print(f"Restored database to {db_path}")
        else:
            # New mode: encrypted tar.gz
            if not args.password:
                print("Error: --password is required for encrypted backups")
                sys.exit(1)

            try:
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa
            except ImportError:
                print("Error: cryptography not installed. Run: pip install cryptography")
                sys.exit(1)

            # Decrypt
            print("Decrypting ...")
            tar_path = os.path.join(tmp_dir, "backup.tar.gz")
            try:
                decrypt_file(local_file, tar_path, args.password)
            except Exception as e:
                print(f"Decryption failed (wrong password?): {e}")
                sys.exit(1)

            # Extract
            print("Extracting ...")
            with tarfile.open(tar_path, "r:gz") as tar:
                # Security: check for path traversal
                for member in tar.getmembers():
                    if member.name.startswith("/") or ".." in member.name:
                        print(f"Error: suspicious path in archive: {member.name}")
                        sys.exit(1)

                extract_dir = os.path.join(tmp_dir, "extracted")
                tar.extractall(extract_dir)

            # Copy files to target
            import shutil

            extracted_data = os.path.join(extract_dir, "data")
            extracted_config = os.path.join(extract_dir, "config")

            if os.path.isdir(extracted_data):
                os.makedirs(data_dir, exist_ok=True)
                for item in os.listdir(extracted_data):
                    src = os.path.join(extracted_data, item)
                    dst = os.path.join(data_dir, item)
                    if os.path.isdir(src):
                        if os.path.exists(dst):
                            shutil.rmtree(dst)
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
                    print(f"  Restored: data/{item}")

            if os.path.isdir(extracted_config):
                os.makedirs(config_dir, exist_ok=True)
                for item in os.listdir(extracted_config):
                    src = os.path.join(extracted_config, item)
                    dst = os.path.join(config_dir, item)
                    shutil.copy2(src, dst)
                    print(f"  Restored: config/{item}")

    print()
    print("=" * 50)
    print("  Restore complete!")
    print("=" * 50)
    print()
    print("Next steps:")
    print("  1. Review restored config: config/config.yaml")
    print("  2. Build and start containers:")
    print("     docker-compose -f docker/docker-compose.yml up -d --build")
    print("  3. Start web service:")
    print("     docker-compose -f docker/docker-compose.yml exec teamgr /workspace/scripts/start_web.sh")
    print("  4. Access: https://your-server-ip:6443")


if __name__ == "__main__":
    main()
