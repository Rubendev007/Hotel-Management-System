def user_role(request):
    if request.user.is_authenticated:
        group = request.user.groups.first()
        return {'role': group.name.lower() if group else ('admin' if request.user.is_superuser else 'guest')}
    return {'role': 'guest'}
