# Espace membres DevAntiq

État : passerelle installée sur le VPS ; contrôle des neuf applications réussi le 18 octobre 2026.
La connexion unique aux sessions internes des applications reste à raccorder.
Le fournisseur OIDC et les associations explicites sont développés localement ;
voir [SSO.md](SSO.md) pour le déploiement et les intégrations encore nécessaires.
La configuration Django remplace la préparation Authelia précédente, qui n’avait pas été déployée.

## Fonctions

- Comptes créés et suspendus par un administrateur ; aucune inscription publique.
- Connexion, déconnexion POST, modification et récupération du mot de passe par e-mail.
- Mots de passe Argon2id ; sessions en base, cookie HTTPS/HttpOnly et protection CSRF.
- Neuf applications, recherche, filtre « Mes accès », affichage des droits réellement attribués.
- Administration des comptes et des accès à `/auth/admin/` ; journal des modifications Django.
- Retrait d’un accès ou suspension pris en compte à la requête suivante.
- Limitation des tentatives de connexion et récupération par IP et identifiant.
- Les administrateurs doivent aussi recevoir les accès aux applications qu’ils utilisent.
- L’interface admin LiveMonitor exige en plus un compte superadministrateur DevAntiq.

## Installer depuis Windows

Depuis la racine du projet :

```powershell
& .\scripts\install-members-vps.ps1
```

Le terminal demande le mot de passe SSH, puis, sur le VPS, les paramètres SMTP
(hôte, port 587 ou 465, identifiant, expéditeur et mot de passe masqué).
Il demande ensuite l’identifiant, l’e-mail et le mot de passe du premier administrateur.
Ne collez aucun mot de passe dans la conversation.

Le script installe dans `/opt/devantiq-members`, construit le conteneur, applique les
migrations et copie les ressources administrateur. La base et les secrets restent
hors de `/var/www`. Les mises à jour conservent `config/runtime.json` et `data/`.
Une base existante est sauvegardée avec l’API de sauvegarde SQLite avant mise à jour.
Les fichiers publics passent par le mécanisme de publication avec comparaison et sauvegarde.

L’intégration Nginx ajoute des directives aux serveurs existants : elle conserve
les proxys, les routes PHP et les chemins de certificats. Les configurations ambiguës,
les protections préexistantes ou les ports applicatifs publics entraînent un arrêt
avec diagnostic, sans désactiver les protections existantes.
Les sauvegardes se trouvent sous `/var/backups/devantiq/` (accès root).

L’utilisation actuelle déclarée est un accès navigateur avec un compte propre à
chaque application. Le contrôle central est installé pour cet usage. Si des clients
WebDAV, webhooks ou agents API sont ajoutés, définir et tester leur mode d’accès
avant utilisation : aucune exception générale `/api/` n’est ouverte.

## Protection et vérifications

- Le port 9092 est lié uniquement à 127.0.0.1 ; Nginx reconstruit les en-têtes.
- Tous les sous-domaines applicatifs utilisent `auth_request`, y compris leurs routes PHP.
- `crm.devantiq.com` redirige vers G1CRM en HTTPS ; LiveMonitor admin reste réservé aux administrateurs autorisés.
- Seuls `/script.js` et `/api/send` d’Umami restent publics pour les statistiques.
- Les emplacements ACME existants restent disponibles pour le renouvellement TLS.
- Le script inspecte les ports TCP connus et les publications Docker pour détecter des origines exposées.
- La commande `verify_gateway` vérifie les redirections sans session sur les racines et les routes sensibles inventoriées, puis active les applications.
- Un service de comptes arrêté bloque l’accès aux applications protégées.

Cette vérification automatique ne remplace pas la recette avec de vrais comptes :
connecter un membre, lui attribuer une application, vérifier l’ouverture et le refus
d’une autre, puis retirer le droit pendant sa session. Vérifier aussi la messagerie
et le fonctionnement de chaque application après connexion.

La connexion DevAntiq n’efface pas les connexions internes existantes. Une vraie
connexion unique nécessite ensuite un raccordement OIDC/SAML ou un mécanisme de
confiance adapté à chaque application. La déconnexion centrale bloque la passerelle,
mais ne détruit pas les sessions internes propres aux applications.

## Administrer

1. Se connecter à `https://devantiq.com/auth/admin/`.
2. Ajouter un utilisateur avec son e-mail et un mot de passe initial fort.
3. Ouvrir sa fiche, ajouter les applications dans « Applications attribuées à ce membre », puis enregistrer.
4. Pour lui permettre de choisir son mot de passe, sélectionner son compte dans la liste puis l’action d’envoi de lien de création/réinitialisation.
5. Pour suspendre un compte, décocher « Actif ». Pour révoquer une application, retirer la ligne correspondante.

Un compte sans application attribuée peut se connecter au portail, sans ouvrir
aucune application. Ne pas cocher « Équipe » ou « Superutilisateur » pour les membres ordinaires.
Le dernier superadministrateur actif ne peut pas être désactivé depuis le formulaire.

## Connexion unique : inventaire préalable

Exécuter `& .\scripts\inspect-sso-vps.ps1` pour relever les images Docker,
versions des projets et bibliothèques d'authentification. Le script ne lit ni les
variables d'environnement, ni les comptes, ni les mots de passe.
Il faut identifier le logiciel derrière Cloud et les versions/éditions exactes
d'Umami, n8n et OmniRoute avant de choisir leurs adaptateurs.
Les projets locaux G1Profil et LiveMonitor ont leur propre authentification par
jetons ; la passerelle seule ne crée pas de session dans ces applications.

Le raccordement devra conserver une identité individuelle et les droits propres
à chaque application, sans copier le mot de passe DevAntiq ni partager un compte
administrateur. Les comptes existants doivent être associés explicitement ; une
égalité d'adresse e-mail ne suffit pas pour fusionner automatiquement des comptes.
Les tests doivent couvrir l'ouverture sans seconde connexion, les accès refusés,
la suspension et la révocation, ainsi que la déconnexion centrale.

Référence n8n : https://docs.n8n.io/deploy/host-n8n/configure-n8n/security/configure-sso
(SSO disponible selon l'offre ; vérifier l'édition installée).

## Maintenance

Si l'installation s'arrête sur les ports LiveMonitor publics 3210, 5173 et 9099,
après confirmation des trois unités systemd par `scripts/inspect-app-ports.ps1`,
exécuter `& .\scripts\finish-members-vps.ps1` depuis PowerShell dans le dépôt.
Ce correctif sauvegarde les sources du VPS, limite leurs écoutes à 127.0.0.1,
redémarre les trois services et vérifie leurs réponses HTTP. En cas d'échec de
cette correction, les sources sont restaurées et les services redémarrés.
Il reprend ensuite le contrôle des origines, la protection Nginx et l'activation
des applications. Les comptes et la configuration SMTP existants sont conservés.
Lors des futures mises à jour de LiveMonitor sur ce VPS, conserver ces écoutes
locales ; une nouvelle copie des sources amont pourrait les réouvrir.

```sh
cd /opt/devantiq-members
docker compose logs --tail 80 members
docker compose exec members python manage.py changepassword IDENTIFIANT
docker compose exec -T members python manage.py clearsessions
```

Les fenêtres de limitation expirées sont nettoyées automatiquement lors des requêtes
suivantes. Sauvegarder ensemble `config/runtime.json` et la base SQLite ; ne pas régénérer
la clé de session à chaque déploiement. Restaurer une base avec le service arrêté.
En cas d’incident de protection, laisser les applications verrouillées plutôt que
retirer la passerelle sur une origine publique.

## Développement et tests

```powershell
$env:DEVANTIQ_DEBUG='1'
.\.venv-members\Scripts\python.exe infrastructure/members/service/manage.py test portal
node scripts/test-members.cjs
python scripts/test-members-deployment.py
.\.venv-members\Scripts\python.exe scripts/preview-members.py
```

L’aperçu local est sur `http://127.0.0.1:8088/membres.html` ; aucun compte de démonstration
n’est créé ou livré. Le mode DEBUG ne doit jamais être activé sur le VPS.
Les vérifications de production Django signalent volontairement l’absence de HSTS
« includeSubDomains » et « preload » : tous les domaines du propriétaire ne sont pas
encore certifiés comme exclusivement HTTPS. Les cookies restent sécurisés en production.

Références : [authentification Django](https://docs.djangoproject.com/en/5.2/topics/auth/default/),
[déploiement Django](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/).
