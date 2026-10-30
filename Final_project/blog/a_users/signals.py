from allauth.account.models import EmailAddress
from allauth.account.signals import user_signed_up
from django.contrib.auth.models import User
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Profile


@receiver(post_save, sender=User)
def user_postsave(sender, instance, created, **kwargs):
    user = instance

    if created:
        Profile.objects.get_or_create(user=user)
    else:
        try:
            email_address = EmailAddress.objects.get_primary(user)
            if email_address and email_address.email != user.email:
                email_address.email = user.email
                email_address.verified = True
                email_address.save()
        except Exception:
            if user.email:
                EmailAddress.objects.create(
                    user=user,
                    email=user.email,
                    primary=True,
                    verified=True,
                )


@receiver(user_signed_up)
def on_user_signed_up(request, user, **kwargs):
    if user.email:
        EmailAddress.objects.filter(user=user, email=user.email).update(verified=True)


@receiver(pre_save, sender=User)
def user_presave(sender, instance, **kwargs):
    if instance.username:
        instance.username = instance.username.lower()
