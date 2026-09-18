"""
ESL Figma AI — Student Database Backup & Restore Service
Creates self-contained, detailed ZIP archives of student profiles and histories,
generates clear Telegram captions with manifest details, and handles restoration.
"""
from __future__ import annotations
import json
import logging
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

logger = logging.getLogger("backup_service")

BASE_DIR = Path(__file__).parent.parent.parent
STUDENTS_DIR = BASE_DIR / "data" / "students"
BACKUPS_DIR = BASE_DIR / "data" / "backups"
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)


def get_students_summary() -> List[Dict[str, Any]]:
    """Inspect data/students directory and return structured metadata for each student."""
    students = []
    if not STUDENTS_DIR.exists():
        return students

    for item in sorted(STUDENTS_DIR.iterdir()):
        if not item.is_dir() or item.name.startswith((".", "_")):
            continue

        profile_file = item / "profile.json"
        lessons_file = item / "lessons.json"

        prof = {}
        if profile_file.exists():
            try:
                with open(profile_file, "r", encoding="utf-8") as f:
                    prof = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read profile {profile_file}: {e}")

        lessons_count = 0
        if lessons_file.exists():
            try:
                with open(lessons_file, "r", encoding="utf-8") as f:
                    lessons_data = json.load(f)
                    if isinstance(lessons_data, list):
                        lessons_count = len(lessons_data)
            except Exception:
                pass

        name = prof.get("name", item.name)
        level = prof.get("level", "A1")
        age = prof.get("age")
        interests = prof.get("interests") or []

        students.append({
            "folder": item.name,
            "id": prof.get("id", item.name),
            "name": name,
            "level": level,
            "age": age,
            "lessons_count": lessons_count,
            "interests": interests[:3],
            "updated_at": prof.get("updated_at")
        })

    return students


def create_backup_archive() -> Tuple[str, Dict[str, Any]]:
    """
    Creates a ZIP archive containing all student records and an embedded manifest.
    Returns (archive_path, manifest_data).
    """
    now = datetime.now()
    date_tag = now.strftime("%Y-%m-%d_%H%M%S")
    archive_name = f"students_backup_{date_tag}.zip"
    archive_path = BACKUPS_DIR / archive_name

    students_summary = get_students_summary()

    manifest = {
        "backup_version": "1.0",
        "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "created_at_human": now.strftime("%d.%m.%Y, %H:%M"),
        "total_students": len(students_summary),
        "students": students_summary,
        "archive_name": archive_name
    }

    # Write manifest temporarily inside data/students for packaging
    temp_manifest = STUDENTS_DIR / "BACKUP_MANIFEST.json"
    with open(temp_manifest, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    total_files = 0
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(STUDENTS_DIR):
            for file in files:
                if file.startswith(".") and file != ".gitkeep":
                    continue
                file_path = Path(root) / file
                arcname = file_path.relative_to(STUDENTS_DIR)
                zf.write(file_path, arcname=str(arcname))
                total_files += 1

    # Clean temporary manifest from data/students
    if temp_manifest.exists():
        temp_manifest.unlink()

    file_size_kb = round(archive_path.stat().st_size / 1024, 1)
    manifest["file_size_kb"] = file_size_kb
    manifest["total_files"] = total_files

    logger.info(f"Created student backup archive: {archive_path} ({file_size_kb} KB, {len(students_summary)} students)")
    return str(archive_path), manifest


def format_backup_caption(manifest: Dict[str, Any]) -> str:
    """
    Formats a user-friendly, detailed Markdown caption for the backup archive.
    """
    date_str = manifest.get("created_at_human", datetime.now().strftime("%d.%m.%Y, %H:%M"))
    total = manifest.get("total_students", 0)
    size_kb = manifest.get("file_size_kb", 0)
    students = manifest.get("students", [])

    lines = [
        "📦 *Резервная копия базы учеников*",
        f"📅 *Создано:* `{date_str}`",
        f"👥 *Всего досье в архиве:* *{total}*",
        ""
    ]

    if students:
        lines.append("📋 *Список учеников:*")
        for s in students:
            name = s.get("name", "Ученик")
            level = s.get("level", "A1")
            age_str = f", {s.get('age')} лет" if s.get("age") else ""
            lessons = s.get("lessons_count", 0)
            lessons_str = f" • {lessons} ур." if lessons > 0 else ""
            
            interests = s.get("interests", [])
            int_str = f" — _{', '.join(interests[:2])}_" if interests else ""

            lines.append(f"▫️ *{name}* ({level}{age_str}){lessons_str}{int_str}")
        lines.append("")
    else:
        lines.append("⚠️ _В базе пока нет сохраненных учеников._\n")

    lines.extend([
        f"💾 *Размер:* `{size_kb} КБ` ({manifest.get('total_files', 0)} файлов)",
        "",
        "ℹ️ *Как восстановить на новом ПК:*",
        "1. Просто перешлите этот файл боту в чат, и он восстановит базу автоматически.",
        "2. Либо распакуйте архив в папку `data/students/` вашего проекта."
    ])

    return "\n".join(lines)


def restore_from_archive(zip_path: str | Path) -> Dict[str, Any]:
    """
    Restores student dossiers from a ZIP archive safely into data/students/.
    Guards against zip-slip directory traversal attacks.
    """
    zip_path = Path(zip_path)
    if not zip_path.exists():
        return {"ok": False, "error": f"Файл архива не найден: {zip_path}"}

    STUDENTS_DIR.mkdir(parents=True, exist_ok=True)

    restored_students = set()
    total_extracted = 0

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                # Prevent Zip-Slip
                target_path = (STUDENTS_DIR / member.filename).resolve()
                if not str(target_path).startswith(str(STUDENTS_DIR.resolve())):
                    logger.warning(f"Skipping dangerous zip member: {member.filename}")
                    continue

                if member.is_dir():
                    target_path.mkdir(parents=True, exist_ok=True)
                    continue

                target_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as source, open(target_path, "wb") as target:
                    shutil.copyfileobj(source, target)
                
                parts = Path(member.filename).parts
                if len(parts) >= 1 and parts[0] not in ("BACKUP_MANIFEST.json", ".gitkeep"):
                    restored_students.add(parts[0])
                total_extracted += 1

        # Clear memory cache in student_agent if available
        try:
            from server.agents import student_agent
            if hasattr(student_agent, "_STUDENTS_CACHE"):
                student_agent._STUDENTS_CACHE = None
        except Exception:
            pass

        return {
            "ok": True,
            "restored_count": len(restored_students),
            "restored_students": list(restored_students),
            "total_files": total_extracted
        }

    except Exception as e:
        logger.error(f"Failed to restore backup: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}
