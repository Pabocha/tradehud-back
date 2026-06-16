"""
Utilitaires pour la gestion des OTP (One-Time Password) et l'envoi d'emails.
"""
import random
import string
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from .models import PasswordResetOTP
from django.utils import timezone


def generate_otp(length=5):
    """
    Génère un code OTP numérique aléatoire.
    
    Args:
        length (int): Longueur du code OTP (défaut: 5)
    
    Returns:
        str: Code OTP généré
    """
    return ''.join(random.choices(string.digits, k=length))


def create_otp_for_email(email):
    """
    Crée un nouveau code OTP pour un email donné.
    Supprime les anciens OTP non utilisés pour cet email.
    
    Args:
        email (str): Adresse email de l'utilisateur
    
    Returns:
        PasswordResetOTP: Objet OTP créé
    """
    # Supprimer les anciens OTP non utilisés pour cet email
    PasswordResetOTP.objects.filter(email=email, is_used=False).delete()
    
    # Générer le nouveau code OTP
    otp_code = generate_otp()
    
    # Créer l'enregistrement
    otp_obj = PasswordResetOTP.objects.create(
        email=email,
        otp=otp_code
    )
    
    return otp_obj


def send_otp_email(email, otp_code):
    """
    Envoie un email avec le code OTP à l'utilisateur.
    
    Args:
        email (str): Adresse email du destinataire
        otp_code (str): Code OTP à envoyer
    
    Returns:
        bool: True si l'email a été envoyé avec succès, False sinon
    """
    try:
        subject = "Votre code de réinitialisation de mot de passe"
        
        # Créer le contexte pour le template
        context = {
            'otp_code': otp_code,
            'expiration_minutes': 10
        }
        
        # Essayer de charger un template HTML personnalisé
        try:
            html_message = render_to_string('email/password_reset_otp.html', context)
            plain_message = strip_tags(html_message)
        except:
            # Si le template n'existe pas, utiliser un message simple
            plain_message = f"""
Votre code de réinitialisation de mot de passe est: {otp_code}

Ce code est valide pendant 10 minutes.

Si vous n'avez pas demandé de réinitialisation, ignorez cet email.
            """
            html_message = plain_message.replace('\n', '<br>')
        
        # Envoyer l'email
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False
        )
        
        return True
        
    except Exception as e:
        print(f"Erreur lors de l'envoi de l'email OTP: {str(e)}")
        return False


def verify_otp(email, otp_code):
    """
    Vérifie si le code OTP fourni est valide pour l'email donné.
    
    Args:
        email (str): Adresse email de l'utilisateur
        otp_code (str): Code OTP à vérifier
    
    Returns:
        dict: {
            'valid': bool,
            'message': str,
            'otp_obj': PasswordResetOTP or None
        }
    """
    try:
        # Chercher l'OTP le plus récent pour cet email
        otp_obj = PasswordResetOTP.objects.filter(
            email=email,
            otp=otp_code,
            is_used=False
        ).latest('created_at')
    except PasswordResetOTP.DoesNotExist:
        return {
            'valid': False,
            'message': "Code OTP invalide ou déjà utilisé.",
            'otp_obj': None
        }
    
    # Vérifier si l'OTP a expiré
    if otp_obj.is_expired():
        return {
            'valid': False,
            'message': "Le code OTP a expiré. Demandez un nouveau code.",
            'otp_obj': None
        }
    
    return {
        'valid': True,
        'message': "Code OTP vérifié avec succès.",
        'otp_obj': otp_obj
    }


def mark_otp_as_used(otp_obj):
    """
    Marque un OTP comme utilisé.
    
    Args:
        otp_obj (PasswordResetOTP): L'objet OTP à marquer
    """
    otp_obj.is_used = True
    otp_obj.used_at = timezone.now()
    otp_obj.save()


def reset_user_password(email, new_password):
    """
    Réinitialise le mot de passe d'un utilisateur.
    
    Args:
        email (str): Email de l'utilisateur
        new_password (str): Nouveau mot de passe
    
    Returns:
        dict: {
            'success': bool,
            'message': str,
            'user': CustomUser or None
        }
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    try:
        user = User.objects.get(email=email)
        user.set_password(new_password)
        user.save()
        
        return {
            'success': True,
            'message': "Mot de passe réinitialisé avec succès.",
            'user': user
        }
    except User.DoesNotExist:
        return {
            'success': False,
            'message': "Utilisateur introuvable.",
            'user': None
        }
