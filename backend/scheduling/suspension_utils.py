"""教师临时停排相关的复用逻辑。

课表是按"周几 + 第几节"描述的周循环结构，而停排登记在具体日期上，
因此通过 date.isoweekday()（1=周一 … 7=周日）把停排映射到周课表的节次。
"""
from datetime import date
from typing import Dict, Iterable, List, Optional, Set, Tuple

from core.models import Semester
from .models import ScheduleEntry, TeacherSuspension


def _parse_holiday(value) -> Optional[date]:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def semester_holidays(semester: Semester) -> Set[date]:
    holidays: Set[date] = set()
    for raw in (semester.holidays or []):
        parsed = _parse_holiday(raw)
        if parsed:
            holidays.add(parsed)
    return holidays


def active_suspensions_for_semester(semester: Semester) -> List[TeacherSuspension]:
    """返回落在学期日期范围内（且不在节假日内）的有效停排。"""
    holidays = semester_holidays(semester)
    suspensions = TeacherSuspension.objects.filter(
        is_active=True,
        date__gte=semester.start_date,
        date__lte=semester.end_date,
    ).order_by('date', 'start_period')
    return [s for s in suspensions if s.date not in holidays]


def suspensions_by_teacher(suspensions: Iterable[TeacherSuspension]) -> Dict[int, List[TeacherSuspension]]:
    mapping: Dict[int, List[TeacherSuspension]] = {}
    for suspension in suspensions:
        mapping.setdefault(suspension.teacher_id, []).append(suspension)
    return mapping


def blocked_teacher_slots(
    suspensions: Iterable[TeacherSuspension]
) -> Dict[int, Set[Tuple[int, int]]]:
    """把停排展开为 教师 -> {(周几, 节次), ...} 的不可排课时段。"""
    blocked: Dict[int, Set[Tuple[int, int]]] = {}
    for suspension in suspensions:
        slots = blocked.setdefault(suspension.teacher_id, set())
        for period in range(suspension.start_period, suspension.end_period + 1):
            slots.add((suspension.day_of_week, period))
    return blocked


def flags_for_entry(
    entry: ScheduleEntry,
    suspension_map: Dict[int, List[TeacherSuspension]]
) -> List[dict]:
    """返回命中某条课表节次的停排标记（锁定课碰到停排时据此单独标出）。"""
    flags = []
    for suspension in suspension_map.get(entry.teacher_id, []):
        if suspension.covers(entry.day_of_week, entry.period):
            flags.append({
                'suspension_id': suspension.id,
                'teacher_id': suspension.teacher_id,
                'date': suspension.date.isoformat(),
                'start_period': suspension.start_period,
                'end_period': suspension.end_period,
                'period_count': suspension.period_count,
                'reason': suspension.reason,
            })
    return flags


def find_suspension_clashes(
    teacher_id: int,
    day_of_week: int,
    period: int,
    suspension_map: Dict[int, List[TeacherSuspension]]
) -> List[TeacherSuspension]:
    """找出某教师在某节次上命中的有效停排。"""
    return [
        s for s in suspension_map.get(teacher_id, [])
        if s.covers(day_of_week, period)
    ]
