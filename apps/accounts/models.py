from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager, Group
from django_countries.fields import CountryField
import uuid
# from apps.vendor.boutique.models import Shops

# Create your models here.


def default_notification_preferences():
    return {
        "all": True,
        "order": True,
        "promo": True,
        "message": True,
        "delivery": True,
        "product": True,
        "support": True,
        "account": True,
    }

class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(
                "Un utilisateur doit avoir obligatoirement un email")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_active', True)
        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractBaseUser):
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        related_name='customuser_set'  # utilisez un nom personnalisé ici
    )
    groups = models.ManyToManyField(Group, blank=True, related_name='user_groups')
    CHOICES_USER = [
        ('acheteur', 'Acheteur'),
        ('vendeur', 'Vendeur'),
        ('deux', 'Les deux')
    ]
    GENDER_CHOICES = [
        ('M', 'Masculin'),
        ('F', 'Feminin'),
    ]

    email = models.EmailField(unique=True, verbose_name='Adresse Email')
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=30, unique=True)
    type_user = models.CharField(max_length=50, choices=CHOICES_USER, default='acheteur')
    country = CountryField(blank_label='(select country)')
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, default='M')
    date_of_birth = models.DateField(blank=True, null=True)
    full_address = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=255, blank=True, null=True)
    has_seller_account = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    # champ soft-delete / timestamp de suppression demandée ou effective
    deleted_at = models.DateTimeField(blank=True, null=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name']

    class Meta:
        db_table = 'utilisateur'

    def __str__(self):
        return self.email

    def has_perm(self, perm, obj=None):
        return True

    def has_module_perms(self, app_label):
        return True
    
class Address(models.Model):
    CHOICES_TYPE = [
        ('shipping', 'Livraison'),
        ('billing', 'Facturation'),
        ('both', 'Les deux'),
    ]

    customer = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='addresses')
    address_type = models.CharField(max_length=20, choices=CHOICES_TYPE, default='shipping')
    
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=30)
    
    street_address = models.TextField(help_text="Rue, appartement, quartier, etc.")
    city = models.CharField(max_length=100)
    state_region = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    country = CountryField(blank_label='(select country)')
    
    is_default = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.city}"

    
class UserProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    photo = models.ImageField(upload_to="images/profile", blank=True, null=True)

class OnlineUser(models.Model):
	user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)

	def __str__(self):
		return self.user.email

class UserSettings(models.Model):
    CURRENCY_CHOICES = [
    ('XOF', 'Franc CFA'),
    ('XAF', 'Franc CFA'),
    ('USD', 'US Dollar'),
    ('EUR', 'Euro'),
    ('GNF', 'Franc Guinéen'),
    # Ajoute ce que tu veux
    ]
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    language = models.CharField(max_length=10, default='fr')
    currency = models.CharField(max_length=5, choices=CURRENCY_CHOICES, default='XOF')
    country = CountryField(blank_label='(select country)')
    notifications_enabled = models.BooleanField(default=True)
    notification_preferences = models.JSONField(
        default=default_notification_preferences,
        blank=True
    )

    def __str__(self):
        return self.user.email




class SellerAccount(models.Model):

    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='seller_account')

    # Identité & contacts
    company_name = models.CharField(max_length=255)  # nom ou raison sociale
    phone_number = models.CharField(max_length=30)
    email_contact = models.EmailField()
    address = models.CharField(max_length=255, blank=True, null=True)

    # Documents officiels
    license_number = models.CharField(max_length=100, blank=True, null=True)
    id_document = models.ImageField(upload_to='seller_docs/', blank=True, null=True)
    proof_of_address_document = models.ImageField(upload_to='seller_docs/', blank=True, null=True)

    # Informations bancaires & fiscales
    bank_account = models.CharField(max_length=100, blank=True, null=True)
    tax_id = models.CharField(max_length=100, blank=True, null=True)
    vat_number = models.CharField(max_length=100, blank=True, null=True)

    # Paramètres & statut
    status = models.CharField(max_length=20, choices=[('pending', 'Inactive'), ('active', 'Active'), ('suspended', 'Suspendu')], default='pending')
    date_created = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    def __str__(self):
        return self.company_name
    

class ShopFollow(models.Model):
    user = models.ForeignKey('accounts.CustomUser', on_delete=models.CASCADE, related_name="followed_shops")
    shop = models.ForeignKey('shops.Shops', on_delete=models.CASCADE, related_name="followers")
    followed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'shop')  

    def __str__(self):
        return f"{self.user} suit {self.shop}"
    


# accounts/models.py (même fichier ou un autre)
class DeletionRequest(models.Model):
    """
    Représente une demande de suppression RGPD initiée par l'utilisateur.
    Un token unique est envoyé par email pour confirmer la demande.
    """
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("processed", "Processed"),
        ("cancelled", "Cancelled"),
    )

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="deletion_requests")
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    requested_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(blank=True, null=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    # date à laquelle la disparition définitive aura lieu automatiquement (optional)
    scheduled_for = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"DeletionRequest({self.user.email}, {self.status})"


class PasswordResetOTP(models.Model):
    """
    Modèle pour stocker les codes OTP pour la réinitialisation de mot de passe.
    Chaque OTP expire après 10 minutes et ne peut être utilisé qu'une seule fois.
    """
    email = models.EmailField()
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        verbose_name = "Password Reset OTP"
        verbose_name_plural = "Password Reset OTPs"
        ordering = ['-created_at']

    def __str__(self):
        return f"OTP for {self.email} (used={self.is_used})"

    def is_expired(self):
        """
        Vérifie si l'OTP a expiré (plus de 10 minutes).
        """
        from django.utils import timezone
        from datetime import timedelta
        return timezone.now() > self.created_at + timedelta(minutes=10)

    def is_valid(self):
        """
        Vérifie si l'OTP est valide (non expiré et non utilisé).
        """
        return not self.is_expired() and not self.is_used
