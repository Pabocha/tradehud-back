# Audit de sécurité – Plan de remédiation (Django / API)

## Contexte
Ce document synthétise l’analyse de sécurité réalisée sur la base de code. Il sert de **référence opérationnelle** pour appliquer les correctifs ultérieurement, de manière progressive et maîtrisée.

L’objectif est de :
- Réduire les risques critiques (fuite de secrets, compromission de comptes)
- Sécuriser l’environnement de production
- Améliorer la robustesse et la maintenabilité du code

---

## 🔴 Problèmes critiques identifiés

### 1. Secrets exposés dans le code
**Fichiers concernés** : `settings.py`

- `SECRET_KEY` en clair
- Mot de passe base de données
- Identifiants email (SMTP)
- Identifiants Elasticsearch

**Risque** : compromission totale de l’application si le dépôt est exposé.

**Action recommandée** :
- Rotation immédiate de tous les secrets
- Suppression définitive des secrets du dépôt Git

---

### 2. Configuration production dangereuse
**Fichiers concernés** : `settings.py`

- `DEBUG = True`
- `ALLOWED_HOSTS = ['*']`

**Risque** :
- Fuite d’informations internes
- Exposition aux attaques XSS / Host Header Injection

**Actions recommandées** :
- `DEBUG = False` en production
- Définir explicitement les domaines autorisés

---

### 3. Elasticsearch non sécurisé
**Fichiers concernés** : `settings.py`

- `verify_certs = False`
- Authentification HTTP en clair

**Risque** : interception des données et des identifiants

**Actions recommandées** :
- Activer la vérification TLS
- Fournir un CA bundle valide

---

### 4. Gestion OTP vulnérable
**Fichiers concernés** : `otp_utils.py`

Problèmes :
- OTP stocké en clair
- `except:` générique
- `print()` pour les erreurs
- Aucune limitation de tentatives

**Risque** :
- Brute force OTP
- Compromission de comptes utilisateurs

**Actions recommandées** :
- Hasher les OTP (HMAC ou bcrypt)
- Comparaison en temps constant
- Limitation des tentatives
- Envoi email asynchrone

---

### 5. Absence de throttling
**Fichiers concernés** : vues d’authentification

- Aucun rate limit sur login / OTP / reset password

**Risque** : attaques par force brute et spam

**Actions recommandées** :
- Activer `DRF throttling`
- Limites par IP et par utilisateur

---

## 🟠 Problèmes importants

### 6. Logs et debugging non sécurisés

- `print()` en production
- Exceptions affichées directement

**Actions recommandées** :
- Utiliser `logging`
- Ne jamais logger de secrets

---

### 7. Gestion des exceptions trop large
**Fichiers concernés** : `serializers.py`, `consumers.py`

- Utilisation de `except:` sans type

**Risque** :
- Bugs silencieux
- Sécurité affaiblie

**Actions recommandées** :
- Exceptions spécifiques
- Messages d’erreur contrôlés

---

### 8. Upload de fichiers non sécurisé

- Aucune validation taille/type
- Stockage local par défaut

**Risque** :
- Upload de fichiers malveillants

**Actions recommandées** :
- Valider MIME et taille
- Stockage cloud (S3, URLs signées)

---

## 🟡 Améliorations recommandées

### 9. Politique JWT

- Tokens trop longs
- Trop de données dans les claims

**Actions recommandées** :
- Réduire la durée de vie
- Supprimer les données sensibles

---

### 10. Automatisation sécurité

**Outils recommandés** :
- Bandit
- safety
- flake8
- pre-commit

---

### 11. Documentation sécurité

- Ajouter une politique de gestion des secrets
- Procédure de rotation en cas de fuite

---

## 📌 Plan d’implémentation recommandé (ordre)

1. Rotation des secrets
2. Externalisation des secrets (variables d’environnement)
3. Sécurisation `settings.py`
4. Correction OTP + throttling
5. Remplacement des `print()` et `except:`
6. Sécurisation des uploads
7. Durcissement JWT
8. Mise en place CI sécurité

---

## ✅ Conclusion

Cette base de code est fonctionnelle mais **non prête pour une exposition publique** sans correctifs.
Les actions proposées sont progressives et peuvent être appliquées via de petits PRs indépendants.

Ce document sert de **checklist de sécurité** pour les prochaines phases du projet.