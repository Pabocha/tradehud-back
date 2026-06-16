# 🔐 Système de Réinitialisation de Mot de Passe avec OTP (One-Time Password)

## 📋 Vue d'ensemble

Ce système remplace entièrement le flux par défaut de Django pour la réinitialisation de mot de passe. Au lieu d'utiliser des liens de réinitialisation HTML, tout est géré via API REST, ce qui le rend compatible avec les applications mobiles (Flutter, React Native, etc.).

### Caractéristiques principales :
- ✅ Génération automatique de codes OTP (4-6 chiffres)
- ✅ Expiration OTP après 10 minutes
- ✅ Single-use (l'OTP ne peut être utilisé qu'une fois)
- ✅ Envoi d'email avec template HTML personnalisé
- ✅ Endpoints API REST dédiés
- ✅ Aucune dépendance sur les vues HTML Django
- ✅ Compatible avec Flutter et autres clients mobiles

---

## 🚀 Endpoints API

### 1. Demander un OTP
**POST** `/api/auth/password/forgot/`

#### Request Body:
```json
{
    "email": "user@example.com"
}
```

#### Response (200):
```json
{
    "detail": "Code OTP envoyé à votre adresse email. Valide pour 10 minutes."
}
```

#### Erreurs possibles:
- **404**: Email inexistant
- **500**: Erreur lors de l'envoi de l'email

---

### 2. Vérifier l'OTP
**POST** `/api/auth/password/verify-otp/`

#### Request Body:
```json
{
    "email": "user@example.com",
    "otp": "123456"
}
```

#### Response (200):
```json
{
    "detail": "Code OTP valide. Vous pouvez maintenant réinitialiser votre mot de passe."
}
```

#### Erreurs possibles:
- **400**: OTP invalide, expiré ou déjà utilisé
- **404**: Email inexistant

---

### 3. Réinitialiser le mot de passe
**POST** `/api/auth/password/reset/`

#### Request Body:
```json
{
    "email": "user@example.com",
    "otp": "123456",
    "new_password": "NewPassword123!",
    "new_password_confirm": "NewPassword123!"
}
```

#### Response (200):
```json
{
    "detail": "Mot de passe réinitialisé avec succès. Vous pouvez maintenant vous connecter."
}
```

#### Erreurs possibles:
- **400**: OTP invalide, mots de passe ne correspondent pas, ou mot de passe trop faible
- **404**: Email inexistant

---

## 📧 Email Template

Le template HTML `templates/email/password_reset_otp.html` est envoyé à l'utilisateur avec :
- Le code OTP formaté de façon visible
- Durée de validité (10 minutes)
- Message d'avertissement de sécurité
- Design moderne et responsive

**Exemple d'email reçu:**
```
Bonjour,

Vous avez demandé une réinitialisation de votre mot de passe. Utilisez le code ci-dessous pour continuer :

┌──────────────────┐
│   123456         │ ← Code OTP
│   ⏱️ Valide 10min  │
└──────────────────┘

⚠️ Important : Ne partagez jamais ce code avec quiconque.
```

---

## 🔧 Fichiers modifiés/créés

### 1. **comptes/models.py**
   - Modèle `PasswordResetOTP` avec expiration automatique
   - Méthode `is_valid()` pour vérifier la validité

### 2. **comptes/otp_utils.py** (nouveau)
   - `generate_otp()` : génère un code aléatoire
   - `create_otp_for_email()` : crée un nouvel OTP
   - `send_otp_email()` : envoie l'email
   - `verify_otp()` : valide l'OTP
   - `mark_otp_as_used()` : marque comme utilisé
   - `reset_user_password()` : réinitialise le mot de passe

### 3. **comptes/serializers.py**
   - `ForgotPasswordSerializer`
   - `VerifyOTPSerializer`
   - `ResetPasswordSerializer`

### 4. **comptes/views.py**
   - `ForgotPasswordView` (GenericAPIView)
   - `VerifyOTPView` (GenericAPIView)
   - `ResetPasswordView` (GenericAPIView)

### 5. **comptes/routers.py**
   - Routes ajoutées pour les 3 endpoints

### 6. **comptes/migrations/0006_passwordresetotp.py**
   - Migration pour créer la table

### 7. **templates/email/password_reset_otp.html**
   - Template email HTML

### 8. **ecommerce/settings.py**
   - `DEFAULT_FROM_EMAIL` ajouté

---

## 🔑 Flux complet (Flutter)

```
┌─────────────────────────────────────────────────────────┐
│ 1. Utilisateur clique "Mot de passe oublié"            │
└─────────────────────────────────────────────────────────┘
                          ↓
    POST /api/auth/password/forgot/
    { "email": "user@example.com" }
                          ↓
      ✉️ Email avec OTP envoyé à l'utilisateur
                          ↓
┌─────────────────────────────────────────────────────────┐
│ 2. Utilisateur entre le code OTP dans l'app mobile     │
└─────────────────────────────────────────────────────────┘
                          ↓
    POST /api/auth/password/verify-otp/
    { "email": "user@example.com", "otp": "123456" }
                          ↓
      ✅ OTP validé (réponse 200)
                          ↓
┌─────────────────────────────────────────────────────────┐
│ 3. Utilisateur entre le nouveau mot de passe           │
└─────────────────────────────────────────────────────────┘
                          ↓
    POST /api/auth/password/reset/
    {
      "email": "user@example.com",
      "otp": "123456",
      "new_password": "NewPass123!",
      "new_password_confirm": "NewPass123!"
    }
                          ↓
      ✅ Mot de passe changé (réponse 200)
                          ↓
┌─────────────────────────────────────────────────────────┐
│ 4. Utilisateur peut se connecter avec nouveau mot de passe
└─────────────────────────────────────────────────────────┘
```

---

## 🛡️ Règles de sécurité

### OTP Expiration
- **Durée de validité**: 10 minutes
- Après 10 minutes, l'utilisateur doit demander un nouveau code

### Single-Use
- Chaque OTP ne peut être utilisé qu'une seule fois
- Après utilisation, il est marqué comme `is_used=True`

### Limite de requêtes (Optionnel)
Pour éviter les spam, tu peux ajouter une limite de requêtes avec Django Throttling :

```python
from rest_framework.throttling import UserRateThrottle

class OTPRateThrottle(UserRateThrottle):
    scope = 'otp'
    rate = '5/hour'  # 5 requêtes par heure
```

Et l'ajouter aux views :
```python
throttle_classes = [OTPRateThrottle]
```

### Validation de mot de passe
- Les mots de passe sont validés selon les règles Django:
  - Minimum 8 caractères
  - Pas similaire à l'email
  - Pas de motifs courants
  - Au moins 1 nombre et 1 caractère spécial (recommandé)

---

## 📱 Exemple Flutter

```dart
// 1. Demander OTP
Future<void> forgotPassword(String email) async {
  final response = await http.post(
    Uri.parse('https://api.example.com/api/auth/password/forgot/'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({'email': email}),
  );
  
  if (response.statusCode == 200) {
    print('OTP sent successfully');
  }
}

// 2. Vérifier OTP
Future<void> verifyOTP(String email, String otp) async {
  final response = await http.post(
    Uri.parse('https://api.example.com/api/auth/password/verify-otp/'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({'email': email, 'otp': otp}),
  );
  
  if (response.statusCode == 200) {
    print('OTP verified');
  }
}

// 3. Réinitialiser mot de passe
Future<void> resetPassword(
  String email,
  String otp,
  String newPassword,
) async {
  final response = await http.post(
    Uri.parse('https://api.example.com/api/auth/password/reset/'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({
      'email': email,
      'otp': otp,
      'new_password': newPassword,
      'new_password_confirm': newPassword,
    }),
  );
  
  if (response.statusCode == 200) {
    print('Password reset successfully');
  }
}
```

---

## 🧪 Tests

Tu peux tester avec curl :

```bash
# 1. Demander OTP
curl -X POST http://localhost:8000/api/auth/password/forgot/ \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com"}'

# 2. Vérifier OTP
curl -X POST http://localhost:8000/api/auth/password/verify-otp/ \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "otp": "123456"}'

# 3. Réinitialiser mot de passe
curl -X POST http://localhost:8000/api/auth/password/reset/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "otp": "123456",
    "new_password": "NewPassword123!",
    "new_password_confirm": "NewPassword123!"
  }'
```

---

## ⚙️ Configuration

### Email
Les emails sont configurés via Gmail SMTP dans `settings.py`:
- `EMAIL_HOST`: smtp.gmail.com
- `EMAIL_PORT`: 587
- `EMAIL_USE_TLS`: True
- `EMAIL_HOST_USER`: pablogenius03@gmail.com
- `DEFAULT_FROM_EMAIL`: pablogenius03@gmail.com

### Templates
Le chemin des templates est configuré dans `settings.py`:
```python
TEMPLATES = [
    {
        'DIRS': [BASE_DIR, 'templates'],
        ...
    }
]
```

---

## 🔄 Étapes de déploiement

1. **Créer la migration**:
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

2. **Tester les emails** (en développement):
   ```python
   # Dans shell Django
   from comptes.otp_utils import create_otp_for_email, send_otp_email
   otp = create_otp_for_email('test@example.com')
   send_otp_email('test@example.com', otp.otp)
   ```

3. **Enregistrer le modèle dans l'admin** (optionnel):
   ```python
   # comptes/admin.py
   from .models import PasswordResetOTP
   admin.site.register(PasswordResetOTP)
   ```

---

## 📝 Notes

- ✅ Les OTP sont stockés en base de données (pas en cache Redis)
- ✅ Aucune dépendance sur le système de tokens Django
- ✅ Les emails utilisent Gmail SMTP (facilement configurable)
- ✅ Compatible avec toutes les versions de Django ≥ 3.2
- ✅ Pas de dépendances externes supplémentaires

---

## 🐛 Dépannage

### Les emails ne s'envoient pas
- Vérifier les credentials Gmail dans `settings.py`
- S'assurer que "Accès des applications moins sécurisées" est activé sur le compte Gmail
- Vérifier les logs Django pour les erreurs SMTP

### OTP continue à être invalide
- Vérifier que l'OTP n'a pas expiré (> 10 minutes)
- Vérifier que l'OTP n'a pas déjà été utilisé
- S'assurer que le bon email est utilisé

### Template email ne s'affiche pas
- Vérifier le chemin du template : `templates/email/password_reset_otp.html`
- S'assurer que les répertoires existent
- Django utilisera un message texte simple si le template n'existe pas

---

## 🎯 Améliorations futures

- [ ] Ajouter rate limiting pour éviter les spam OTP
- [ ] Ajouter une table d'audit pour les tentatives failed
- [ ] Intégrer un service SMS pour l'OTP (Twilio, African's Talking)
- [ ] Ajouter la double authentification (2FA) avec OTP
- [ ] Notifier l'utilisateur si la réinitialisation échoue

---

**Créé le**: Novembre 2025  
**Version**: 1.0  
**Statut**: ✅ Production Ready
