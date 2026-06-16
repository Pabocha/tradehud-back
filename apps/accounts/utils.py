# accounts/utils.py
from django.utils import timezone

def anonymize_user(user):
    """
    Anonymise un utilisateur : remplace email / nom / téléphone, désactive le compte.
    Conserver les FK (ex: commandes) mais sans info perso.
    """
    timestamp = int(timezone.now().timestamp())
    user.email = f"deleted_user_{user.id}_{timestamp}@example.invalid"
    user.first_name = ""
    user.last_name = ""
    user.phone_number = ""
    user.full_address = ""
    user.city = ""
    user.postal_code = ""
    user.country = None  # si CountryField accepte None
    user.country_code = ""
    user.latitude = None
    user.longitude = None
    user.has_seller_account = False
    user.is_active = False
    user.deleted_at = timezone.now()
    # révoquer les groupes/permissions sensibles si nécessaire
    user.groups.clear()
    user.user_permissions.clear()
    user.save()

def hard_delete_user(user):
    # avant suppression, déplacer / anonymiser les objets liés qui ne peuvent pas être supprimés
    user.delete()
