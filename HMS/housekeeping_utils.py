from django.contrib.auth.models import User, Group
from accounts.models import Employee, Task
from room.models import Room

CLEANING_WEIGHTS = {
    'King': 2.0,
    'Luxury': 1.5,
    'Normal': 1.0,
    'Economic': 0.5,
}


def get_cleaning_weight(room):
    return CLEANING_WEIGHTS.get(room.roomType, 1.0)


def get_staff_users():
    return User.objects.filter(groups__name='staff').distinct()


def staff_workload(staff_user):
    tasks = Task.objects.filter(
        employee=staff_user.employee,
        category='cleaning',
        status__in=['pending', 'in_progress']
    ).select_related('room')
    total = 0.0
    for t in tasks:
        if t.room:
            total += get_cleaning_weight(t.room)
        else:
            total += 1.0
    return total


def assign_housekeeping_task(room):
    staff_users = get_staff_users()
    if not staff_users.exists():
        return None
    chosen = min(staff_users, key=lambda u: staff_workload(u))
    Task.objects.create(
        employee=chosen.employee,
        room=room,
        category='cleaning',
        status='pending',
        description=f"Clean Room {room.number} ({room.roomType})"
    )
    return chosen


def rebalance_cleaning_tasks():
    staff_users = list(get_staff_users())
    if not staff_users:
        return 0
    cleaning_tasks = Task.objects.filter(
        category='cleaning', status='pending'
    ).select_related('room').order_by('id')
    for task in cleaning_tasks:
        chosen = min(staff_users, key=lambda u: staff_workload(u))
        task.employee = chosen.employee
        task.save()
    return cleaning_tasks.count()
