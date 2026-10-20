# Connexion unique — état du raccordement

## État confirmé et travail en cours (19 octobre)

Les sources VPS ont maintenant été reçues et les adaptateurs G1CRM, G1Profil,
LiveMonitor et SentiNet ont été développés localement. Le paquet se déploie par
`scripts/install-native-sso-vps.ps1` ; il n'a pas encore été exécuté sur le VPS.
Voir `adapters/README.md` pour les droits, le contrôle d'identité, les sauvegardes
et les limites. SentiNet est volontairement en lecture seule pour les comptes SSO.
Les identités dédiées sont créées pour les accès attribués ; les comptes natifs
sont créés lors de leur première connexion et les comptes existants sont conservés.
Les tests locaux du portail, des cartes et du connecteur OIDC passent (49 tests).
Ils incluent un échange avec jeton RSA signé, le rejet d'un nonce incorrect,
l'usage unique du retour, le MFA et le changement d'identité de session.

Les mentions ci-dessous indiquant que les quatre adaptateurs restent à développer
sont l'historique de l'inspection ; leur déploiement et leur recette réelle restent
à faire. Umami, Zabbix et OmniRoute restent à raccorder séparément.

Le propriétaire a validé la connexion Cloud après correction du callback vers
`https://cloud.devantiq.com/apps/user_oidc/code`. Ne pas réinstaller ce connecteur
ni recréer son compte. L'édition n8n est Community : sa connexion interne demeure,
la fonction SSO native n'étant pas disponible dans cette édition.

Développé localement, non déployé : le catalogue membres lit désormais toutes les
applications en base ; les nouvelles cartes disposent d'un repli sur les initiales
si leurs visuels sont absents. Un superadministrateur peut déclarer une application
(désactivée par défaut). Le champ `SSOClient.login_path` indique un chemin SSO
explicitement vérifié. `/auth/apps/<slug>/open/` revérifie l'accès, l'activation et
l'association avant de rediriger vers ce chemin sur le sous-domaine exact.
Un chemin vide conserve l'ouverture habituelle. Aucune activation SSO, attribution
ou création de compte distante n'est réalisée par cette migration.

Pour toute future application : configurer et vérifier son sous-domaine et sa
passerelle Nginx, intégrer son client OIDC, tester les comptes et rôles, puis
renseigner le chemin de lancement et activer son client. La déclaration dans le
catalogue ne remplace pas ces étapes. `protect_apps.py` et la vérification des
origines restent limités aux neuf hôtes inventoriés : les futurs hôtes doivent
être ajoutés à ces procédures avant activation.

Prochaine étape pour G1CRM, G1Profil, SentiNet et LiveMonitor : exécuter
`scripts/fetch-sso-sources-vps.ps1`. Ce script copie uniquement les sources
sélectionnées et leurs empreintes dans une archive privée sous `.vps-inspection`,
afin d'adapter les versions effectivement installées. Les autres connecteurs
ne sont pas encore implémentés/déployés. Umami exige encore une intégration
compatible ; Zabbix une configuration d'authentification HTTP ou SAML ; OmniRoute
ne doit pas ouvrir son administration commune à des membres ordinaires.

Le 18 octobre 2026, le propriétaire a confirmé : conserver les comptes applicatifs
existants et leurs données. Aucun utilisateur applicatif ne doit être recréé ou
fusionné automatiquement à partir de son adresse e-mail.

Le 19 octobre, le propriétaire a demandé de créer de nouveaux comptes dédiés et
de les associer à `hgomis`. Cette instruction remplace la demande d'identifiants
existants ci-dessous : les autres comptes restent conservés. L'objectif reste les
neuf applications, mais leur raccordement global n'est pas encore opérationnel.

Pour le premier raccordement Cloud, la commande locale préparée est :

```powershell
& .\scripts\connect-cloud-sso-vps.ps1 -Member 'hgomis' -CreateCloudUser
```

Elle propose `devantiq-hgomis`, crée un compte Nextcloud standard sans groupe
administrateur, avec un mot de passe aléatoire généré dans Nextcloud et jamais
transmis ou enregistré par le script. Le membre utilisera la connexion DevAntiq.
Le compte commence désactivé ; le script contrôle son identité et ses droits
avant activation et association. En cas d'échec ultérieur, il tente de le
désactiver sans le supprimer, et conserve un relevé privé dans la sauvegarde.
Un compte homonyme ou une association déjà présente bloque la création ; aucun
compte existant n'est réaffecté. Cette option reste limitée au premier
raccordement OIDC : une configuration existante doit être examinée avant reprise.
La création et la connexion réelles restent à exécuter et vérifier sur le VPS.

Après un échec de `user_oidc:provider`, le script distingue désormais les étapes
d'inventaire, de création et de vérification. Le secret est lu par `php://stdin`
au lieu de `/dev/stdin` (toujours transmis par pipe). La cause exacte du code 1
rapporté n'était pas exposée par l'ancien diagnostic ; cette correction reste à
valider sur le VPS. Les erreurs connues sont traduites sans afficher les sorties
brutes. Une reprise des trois réglages partiels est permise uniquement si leurs
valeurs sont exactement celles attendues et si le client privé correspond à un
client DevAntiq désactivé ; tout fournisseur déjà présent reste bloquant.

## Ce qui est développé

DevAntiq expose un fournisseur OpenID Connect sous `/auth/oidc/`. Il utilise la
bibliothèque Django OAuth Toolkit 3.4.1 : codes à usage unique, PKCE, signature
RS256, audience et URI de retour exactes. Les mots de passe ne sortent pas du
service membres. La clé privée reste dans `config/oidc-private.pem` sur le VPS.
Les jetons expirent après cinq minutes ; les renouvellements longue durée et
l'enregistrement public de clients ne sont pas proposés.

L'émission et l'utilisation d'un jeton nécessitent un compte actif, un accès
attribué, une application activée, un client SSO activé et une association de
compte explicite. `sub` identifie le membre DevAntiq ; `external_account` et
`preferred_username` contiennent l'identifiant applicatif validé par l'administrateur.
L'e-mail n'est pas déclaré vérifié. Aucun rôle administrateur n'est transmis.

La déconnexion DevAntiq révoque ses codes et jetons. La passerelle bloque ensuite
les accès navigateur. La destruction des sessions natives dans les applications
reste à intégrer et tester, notamment en cas de changement de membre sur un même
navigateur ; ne pas annoncer une déconnexion unique complète à ce stade.

## Déploiement du fournisseur

`scripts/install-members-vps.ps1` sauvegarde les sources, les secrets existants et
SQLite, conserve SMTP et les comptes, ajoute la clé privée si absente, puis
reconstruit le service. Aucune association ni activation SSO n'est créée par cette
installation. Les accès actuels continuent à fonctionner comme précédemment.

La découverte sera à :
`https://devantiq.com/auth/oidc/.well-known/openid-configuration`

Les clients se préparent avec `manage.py configure_sso_client APPLICATION CALLBACK`,
uniquement après avoir vérifié le callback dans l'application installée.
Le secret est enregistré dans `/data/sso-clients/APPLICATION.json`, jamais affiché.
Il doit être transféré localement vers la configuration privée de l'application.
Les clients sont désactivés par défaut et ne doivent être activés qu'après recette.

Dans l'administration, « Comptes applicatifs associés » permet à un superadministrateur
d'associer un accès existant à l'identifiant exact d'un compte applicatif.
Ne pas donner un compte applicatif privilégié à un membre ordinaire.

## Applications : ce qui reste à raccorder

| Application | Éléments confirmés | Étape restante |
| --- | --- | --- |
| G1CRM | Projet Node `/opt/g1crm/project` | Adapter son authentification et vérifier les comptes/rôles existants |
| G1Profil | Application 3.5.0 ; serveur Node 1.0.0 | Adapter les sessions internes et les comptes existants |
| SentiNet | Node 1.0.0 `/var/www/sentinet/sentinet-app` | Adapter son authentification et vérifier les droits |
| LiveMonitor | Backend Node 1.0.0 ; JWT natifs | Adapter la création de session sans modifier le rôle existant |
| Cloud | Nextcloud 29.0.16 ; aucun module OIDC installé lors du relevé | Script de raccordement prêt ; recette avec un compte existant requise |
| n8n | 2.36.8 | Confirmer l'offre SSO ; ne pas contourner une restriction de licence |
| Umami | 3.3.1 | Confirmer le mécanisme pris en charge ; aucun remplacement par un fork non examiné |
| OmniRoute | 3.8.50 ; OIDC ouvre le tableau de bord administrateur commun | Réserver ce raccordement aux administrateurs désignés, pas aux membres ordinaires |
| Zabbix | Frontend 7.4.14 | Raccorder une méthode prise en charge (HTTP/SAML), conserver les rôles et comptes existants |

Le fournisseur seul ne suffit pas à connecter un membre dans ces applications.
Le script `scripts/inspect-sso-vps.ps1` relève les versions exactes et les modules
Nextcloud en lecture seule. Les tags `latest` ne constituent pas une version.

## Vérification des sources locales du 19 octobre 2026

Objectif confirmé : une session DevAntiq doit ouvrir la session applicative de
chaque membre autorisé, tout en conservant les comptes et leurs données. Un accès
Nginx autorisé n'est pas une connexion dans l'application. Les sources locales
ci-dessous ont été examinées ; leur identité avec les sources du VPS reste à
vérifier avant déploiement.

- G1CRM : `project/server/index.js` émet un JWT depuis le compte existant ;
  `src/context/AuthContext.tsx` reçoit le jeton et le profil. Le raccordement doit
  couvrir le serveur et la réception de session dans le navigateur.
- G1Profil : `project/server/src/index.js` crée les sessions et jetons de
  rafraîchissement ; `src/auth.js` vérifie également `is_active` en base. Réutiliser
  ces contrôles et les rôles du compte local.
- LiveMonitor : `backend/routes/auth.js` retrouve le compte par `username` et
  utilise `signToken`. Vérifier le statut du compte avant toute session SSO.
- SentiNet : `server/index.js` distingue les sessions `mfa` et `session`. Le SSO
  doit conserver l'étape MFA lorsque celle-ci est activée ; une connexion DevAntiq
  seule ne justifie pas de supprimer ce contrôle.

Les identifiants des comptes à associer à `hgomis` dans les huit applications hors
Cloud ont été demandés au propriétaire. Ne pas déduire ces associations d'un nom
identique ou d'une adresse e-mail. Cloud reste explicitement `hgomis` → `admin`.

La documentation n8n consultée le 19 octobre confirme le SSO pour les offres
auto-hébergées Business et Enterprise. L'édition/licence de l'instance doit être
confirmée avant configuration ; la version 2.36.8 seule ne suffit pas.
Source : https://docs.n8n.io/deploy/host-n8n/configure-n8n/security/configure-sso

Aucun raccordement supplémentaire n'a été déployé lors de cette inspection.

## Premier raccordement Cloud

Le fournisseur DevAntiq répond en production (découverte vérifiée le 18 octobre).
Exécuter `scripts/connect-cloud-sso-vps.ps1` : le terminal demande les deux
identifiants existants puis les mots de passe SSH. Le membre doit déjà avoir
l'accès Cloud ; le script ne l'accorde pas implicitement. Il refuse de lier un
compte administrateur Nextcloud à un membre DevAntiq non superadministrateur.

Le script sauvegarde la configuration Nextcloud et SQLite, installe `user_oidc`
depuis le catalogue officiel (version compatible 8.4.x à 8.x seulement), et
configure `auto_provision=false`, PKCE, aucune attribution de groupe et aucune
identité dérivée d'un e-mail. Les profils, quotas et fichiers restent ceux des
comptes existants. Le secret client passe par stdin, pas par la ligne de commande.
Une configuration OIDC déjà présente nécessite un examen et n'est pas écrasée.
En cas d'échec après installation, le script tente de désactiver le module et le
client SSO ; il conserve les sauvegardes et indique si la désactivation a échoué.
Il ne restaure pas automatiquement la base entière ni les autres réglages.

Après succès, tester dans une fenêtre privée : DevAntiq, puis Cloud, puis bouton
DevAntiq sur la page Nextcloud. Vérifier le compte affiché et ses fichiers, puis
le refus après retrait de l'accès. Ce test réel reste nécessaire ; les tests
locaux couvrent les contrôles de correspondance et la non-divulgation des secrets.
Le bouton de la carte conserve l'adresse habituelle de Cloud pendant cette recette.

Référence du comportement OmniRoute :
https://github.com/diegosouzapw/OmniRoute/blob/release/v3.8.50/docs/architecture/AUTHZ_GUIDE.md

Références :
- https://django-oauth-toolkit.readthedocs.io/en/latest/oidc.html
- https://github.com/nextcloud/user_oidc
- https://docs.n8n.io/deploy/host-n8n/configure-n8n/security/configure-sso
