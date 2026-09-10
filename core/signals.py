from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from .models import AuditLog

def ip(request):
    if not request: return None
    f=request.META.get('HTTP_X_FORWARDED_FOR')
    return (f.split(',')[0].strip() if f else request.META.get('REMOTE_ADDR')) or None

@receiver(user_logged_in)
def logged_in(sender,request,user,**kwargs):
    AuditLog.objects.create(user=user,action='LOGIN_SUCCESS',entity_type='User',entity_id=str(user.pk),ip_address=ip(request))

@receiver(user_logged_out)
def logged_out(sender,request,user,**kwargs):
    if user and user.is_authenticated: AuditLog.objects.create(user=user,action='LOGOUT',entity_type='User',entity_id=str(user.pk),ip_address=ip(request))

@receiver(user_login_failed)
def login_failed(sender,credentials,request,**kwargs):
    AuditLog.objects.create(action='LOGIN_FAILED',entity_type='Authentication',description=f"Username: {credentials.get('username','')}",ip_address=ip(request))
