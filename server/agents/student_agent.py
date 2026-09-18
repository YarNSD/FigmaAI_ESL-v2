"""
ESL Figma AI — Student Memory & CRM Agent
Manages individual student dossiers, learning history, strengths/weaknesses,
and personal preferences to tailor educational materials.
"""
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger("student_agent")

STUDENTS_DIR = Path(__file__).parent.parent.parent / "data" / "students"
STUDENTS_DIR.mkdir(parents=True, exist_ok=True)


def _slugify(name: str) -> str:
    """Create a URL- and filesystem-safe slug from a student name."""
    s = name.strip().lower()
    translit = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
    }
    res = []
    for ch in s:
        if ch in translit:
            res.append(translit[ch])
        elif ch.isalnum() or ch in ('-', '_'):
            res.append(ch)
        elif ch.isspace():
            res.append('_')
    out = "".join(res).strip('_')
    return out or f"student_{int(datetime.now().timestamp())}"


def get_name_declensions(name: str) -> Dict[str, str]:
    """Return common Russian cases for a student name (Маша -> Маши, Маше, Машу, Машей)."""
    if not name:
        return {"nom": "", "gen": "", "dat": "", "acc": "", "ins": "", "prep": ""}
    n = name.strip()
    if n.endswith('а'):
        stem = n[:-1]
        return {
            "nom": n,
            "gen": stem + 'и',
            "dat": stem + 'е',
            "acc": stem + 'у',
            "ins": stem + 'ей',
            "prep": stem + 'е'
        }
    if n.endswith('я'):
        stem = n[:-1]
        return {
            "nom": n,
            "gen": stem + 'и',
            "dat": stem + 'е',
            "acc": stem + 'ю',
            "ins": stem + 'ей',
            "prep": stem + 'е'
        }
    if n[-1] not in ('а', 'я', 'и', 'е', 'у', 'ю', 'о', 'ь'):
        return {
            "nom": n,
            "gen": n + 'а',
            "dat": n + 'у',
            "acc": n + 'а',
            "ins": n + 'ом',
            "prep": n + 'е'
        }
    return {"nom": n, "gen": n, "dat": n, "acc": n, "ins": n, "prep": n}


def list_students() -> List[Dict[str, Any]]:
    """Return summary list of all registered students."""
    students = []
    if not STUDENTS_DIR.exists():
        return students

    for p in STUDENTS_DIR.iterdir():
        if p.is_dir():
            prof_path = p / "profile.json"
            if prof_path.exists():
                try:
                    with open(prof_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        lessons_count = 0
                        lessons_path = p / "lessons.json"
                        if lessons_path.exists():
                            with open(lessons_path, "r", encoding="utf-8") as lf:
                                lessons_data = json.load(lf)
                                lessons_count = len(lessons_data) if isinstance(lessons_data, list) else 0

                        students.append({
                            "id": data.get("id", p.name),
                            "name": data.get("name", p.name.capitalize()),
                            "age": data.get("age"),
                            "level": data.get("level", "A1"),
                            "interests": data.get("interests", []),
                            "lessons_count": lessons_count,
                            "updated_at": data.get("updated_at", "")
                        })
                except Exception as e:
                    logger.warning(f"Failed to read student profile at {prof_path}: {e}")

    # Sort alphabetically by name
    students.sort(key=lambda s: s.get("name", "").lower())
    return students


def get_student(student_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve full student profile and lesson history."""
    if not student_id:
        return None
    s_dir = STUDENTS_DIR / student_id
    if not s_dir.exists():
        # Try matching by name
        for p in STUDENTS_DIR.iterdir():
            if p.is_dir():
                prof_p = p / "profile.json"
                if prof_p.exists():
                    try:
                        with open(prof_p, "r", encoding="utf-8") as f:
                            d = json.load(f)
                            if d.get("name", "").lower() == student_id.lower() or d.get("id") == student_id:
                                s_dir = p
                                break
                    except Exception:
                        pass

    if not s_dir.exists():
        return None

    prof_path = s_dir / "profile.json"
    if not prof_path.exists():
        return None

    try:
        with open(prof_path, "r", encoding="utf-8") as f:
            profile = json.load(f)

        lessons = []
        lessons_path = s_dir / "lessons.json"
        if lessons_path.exists():
            with open(lessons_path, "r", encoding="utf-8") as lf:
                lessons = json.load(lf)

        profile["lessons"] = lessons
        return profile
    except Exception as e:
        logger.error(f"Error reading student {student_id}: {e}")
        return None


def save_student(data: Dict[str, Any]) -> Dict[str, Any]:
    """Create or update a student profile."""
    name = data.get("name", "").strip()
    if not name:
        raise ValueError("Student name is required")

    student_id = data.get("id") or _slugify(name)
    s_dir = STUDENTS_DIR / student_id
    s_dir.mkdir(parents=True, exist_ok=True)

    prof_path = s_dir / "profile.json"
    existing = {}
    if prof_path.exists():
        try:
            with open(prof_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = {}

    now_iso = datetime.now().isoformat()
    updated = {
        "id": student_id,
        "name": name,
        "age": data.get("age") if data.get("age") is not None else existing.get("age"),
        "gender": data.get("gender") or existing.get("gender", ""),
        "level": data.get("level") or existing.get("level", "A1"),
        "interests": list(set(data.get("interests", []) or existing.get("interests", []))),
        "strengths": list(set(data.get("strengths", []) or existing.get("strengths", []))),
        "weaknesses": list(set(data.get("weaknesses", []) or existing.get("weaknesses", []))),
        "preferred_format": data.get("preferred_format") or existing.get("preferred_format", "game"),
        "notes": data.get("notes") or existing.get("notes", ""),
        "created_at": existing.get("created_at", now_iso),
        "updated_at": now_iso
    }

    with open(prof_path, "w", encoding="utf-8") as f:
        json.dump(updated, f, ensure_ascii=False, indent=2)

    logger.info(f"Student profile saved: {name} (ID: {student_id})")
    return updated


def record_lesson(student_id: str, lesson_data: Dict[str, Any]) -> bool:
    """Append a completed lesson to the student's history."""
    s = get_student(student_id)
    if not s:
        return False

    s_dir = STUDENTS_DIR / s["id"]
    lessons_path = s_dir / "lessons.json"
    lessons = []
    if lessons_path.exists():
        try:
            with open(lessons_path, "r", encoding="utf-8") as f:
                lessons = json.load(f)
        except Exception:
            lessons = []

    lesson_entry = {
        "lesson_id": f"lesson_{int(datetime.now().timestamp())}",
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "topic": lesson_data.get("topic", "General English"),
        "goal": lesson_data.get("goal", ""),
        "format": lesson_data.get("format", "game"),
        "blocks": lesson_data.get("blocks", []),
        "summary": lesson_data.get("summary", ""),
        "teacher_notes": lesson_data.get("teacher_notes", "")
    }
    lessons.append(lesson_entry)

    with open(lessons_path, "w", encoding="utf-8") as f:
        json.dump(lessons, f, ensure_ascii=False, indent=2)

    logger.info(f"Recorded lesson for {s['name']}: {lesson_entry['topic']}")
    return True


def format_student_prompt_context(student_id: Optional[str]) -> str:
    """Format an informative context block about the student for LLM system prompts."""
    if not student_id:
        return ""

    student = get_student(student_id)
    if not student:
        return ""

    lines = [
        f"УЧЕНИК ДЛЯ УРОКА:",
        f"- Имя: {student.get('name')}",
    ]
    if student.get("age"):
        lines.append(f"- Возраст: {student.get('age')} лет")
    if student.get("level"):
        lines.append(f"- Уровень CEFR: {student.get('level')}")
    if student.get("interests"):
        lines.append(f"- Увлечения и интересы: {', '.join(student.get('interests'))}")
    if student.get("strengths"):
        lines.append(f"- Сильные стороны: {', '.join(student.get('strengths'))}")
    if student.get("weaknesses"):
        lines.append(f"- Слабые стороны (требующие отработки): {', '.join(student.get('weaknesses'))}")
    if student.get("preferred_format"):
        lines.append(f"- Предпочитаемый стиль: {student.get('preferred_format')}")

    lessons = student.get("lessons", [])
    if lessons:
        last_topics = [l.get("topic") for l in lessons[-3:] if l.get("topic")]
        if last_topics:
            lines.append(f"- Ранее изученные темы (не повторять, а связывать): {', '.join(last_topics)}")

    lines.append("ПРАВИЛО ПЕРСОНАЛИЗАЦИИ: Обязательно адаптируй примеры, сюжеты картинок и лексику под интересы и возраст этого ученика!")
    return "\n".join(lines)


def update_student_level(student_id: str, new_level: str) -> Optional[Dict[str, Any]]:
    """Update student's permanent CEFR level."""
    s = get_student(student_id)
    if not s:
        return None
    s["level"] = new_level
    return save_student(s)


def check_level_suggestion(student_id: str, current_selection_level: str) -> Optional[Dict[str, Any]]:
    """Check if the teacher has repeatedly chosen a level different from student's profile."""
    if not student_id or not current_selection_level:
        return None
    s = get_student(student_id)
    if not s:
        return None
    prof_level = s.get("level", "A1")
    if prof_level.upper() == current_selection_level.upper():
        return None

    lessons = s.get("lessons", [])
    override_count = 1  # current choice
    for les in reversed(lessons):
        if les.get("level", "").upper() == current_selection_level.upper():
            override_count += 1
        else:
            break

    if override_count >= 2:
        return {
            "suggest_update": True,
            "student_id": s["id"],
            "student_name": s["name"],
            "current_level": prof_level,
            "new_level": current_selection_level,
            "override_count": override_count,
            "message": f"Заметил, что для {s['name']} вы уже {override_count}-й раз выбираете уровень {current_selection_level} (в профиле указан {prof_level}). Хотите обновить постоянный уровень в профиле ученика на {current_selection_level}?"
        }
    return None


def match_student_in_text(text: str) -> Optional[Dict[str, Any]]:
    """
    Scans text to find mentions of registered students (e.g. "для Маши", "у Маши", "задание для Васи").
    Also handles inflections/cases (Маша, Маши, Маше, Машу, Машей).
    """
    if not text:
        return None
    text_lower = text.lower()
    students = list_students()

    for s in students:
        s_name = s.get("name", "").strip()
        if not s_name or len(s_name) < 2:
            continue

        name_lower = s_name.lower()
        # Stem of Russian name (e.g. "маш" for "Маша", "вас" for "Вася", "миш" for "Миша")
        stem = name_lower[:-1] if name_lower[-1] in ('а', 'я', 'и', 'е', 'у', 'ю', 'о') and len(name_lower) >= 4 else name_lower

        pattern = r"\b" + re.escape(stem) + r"\w*\b"
        if re.search(pattern, text_lower):
            return get_student(s["id"])

    # If student is not registered, detect explicit mention: "ученица Маша", "для Маши", "девочка Маша"
    m = re.search(r"(?:учениц[аеы]|ученик[аеу]?|для|зовут|студент[аеу]?)\s+([А-ЯЁA-Z][а-яёa-z]+)", text)
    if m:
        cand_name = m.group(1).capitalize()
        # Simple lemmatization of Russian name cases
        if cand_name.endswith(('и', 'е', 'у', 'ей')):
            if cand_name.endswith(('ше', 'ши', 'шу', 'шей')):
                cand_name = cand_name[:-1] + 'а'
            elif cand_name.endswith(('се', 'си', 'сю', 'сей')):
                cand_name = cand_name[:-1] + 'я'
            elif cand_name.endswith(('те', 'ти', 'тю', 'тей')):
                cand_name = cand_name[:-1] + 'я'

        stop_words = ["Урока", "Занятия", "Меню", "Квиза", "Блока", "Доски", "Холста", "Слов", "Карточек"]
        if cand_name not in stop_words and len(cand_name) >= 3:
            new_st = save_student({
                "name": cand_name,
                "level": "A1"
            })
            return new_st

    return None


def record_student_feedback(student_id: str, feedback_text: str) -> Dict[str, Any]:
    """
    Parses feedback about a lesson and updates the student dossier with:
    - new strengths / liked formats
    - weaknesses / struggles
    - appends lesson entry
    """
    s = get_student(student_id)
    if not s:
        return {"ok": False, "error": "Student not found"}

    fb_lower = feedback_text.lower()
    strengths_added = []
    weaknesses_added = []

    liked_patterns = [
        (r"(?:понравил[оаи]сь?|заш[её]л|любит|хорошо|легко|отлично)\s+([^.,;\n]+)", "strength"),
        (r"(?:трудн[оа]|сложн[оа]|пута[ею]тся|ошиба[ею]тся|не получ|плохо с|забыва[ею]т)\s+([^.,;\n]+)", "weakness")
    ]
    for pat, kind in liked_patterns:
        matches = re.findall(pat, fb_lower)
        for m in matches:
            cleaned = m.strip()[:40]
            if len(cleaned) >= 3:
                if kind == "strength":
                    strengths_added.append(cleaned)
                else:
                    weaknesses_added.append(cleaned)

    curr_str = s.get("strengths", [])
    curr_weak = s.get("weaknesses", [])
    if strengths_added:
        s["strengths"] = list(set(curr_str + strengths_added))
    if weaknesses_added:
        s["weaknesses"] = list(set(curr_weak + weaknesses_added))

    record_lesson(student_id, {
        "topic": "Урок (по фидбеку)",
        "teacher_notes": feedback_text,
        "summary": f"Сильные стороны: {', '.join(strengths_added) or '—'}, зоны роста: {', '.join(weaknesses_added) or '—'}"
    })
    updated = save_student(s)

    return {
        "ok": True,
        "student": updated,
        "strengths_added": strengths_added,
        "weaknesses_added": weaknesses_added
    }

