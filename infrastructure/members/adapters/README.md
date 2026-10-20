# Connecteurs applicatifs DevAntiq

Ces adaptateurs ciblent les sources VPS récupérées le 19 octobre 2026 dans
`.vps-inspection/sso-sources-66bfc56f35b743c78e338e0443bd3793/sources.tar.gz`.
Ils ne sont pas encore validés par une connexion navigateur sur le VPS.

`scripts/install-native-sso-vps.ps1` construit et transfère le paquet, vérifie
les empreintes des cinq fichiers applicatifs, les cibles de redémarrage distinctes,
leur version Node et leurs écoutes locales, puis sauvegarde les sources et le
service membres. Il met à jour le portail, installe les adaptateurs, redémarre
les quatre services, vérifie les routes et active les clients. Un changement
de source, un gestionnaire non reconnu ou un Node incompatible
interrompt l'installation avant toute modification applicative.

G1CRM et SentiNet utilisent le démon PM2 existant de root (`/root/.pm2`).
L'identifiant est découvert dans le processus, puis confirmé avec son PID et
son chemin source via `pm2 jlist` (sortie privée, jamais affichée). Seul cet
identifiant est redémarré, sans `--update-env`, `restart all`, ni redémarrage du
démon. Le mode cluster et la surveillance automatique des fichiers sont refusés.
G1Profil et LiveMonitor utilisent leurs services systemd dédiés. Ces contrôles
s'appliquent aussi au choix de la cible pendant une restauration.

Node 20.19+, 22.12+ ou 24+ est requis, notamment pour le chargement du module ESM
depuis SentiNet. `openid-client` 6.8.8 est verrouillé avec son fichier npm lock.
Le paquet contient les dépendances JavaScript ; aucune dépendance native des
applications n'est reconstruite. Aucun secret client n'est inclus dans le paquet.

## Identités et droits

Chaque accès attribué obtient une identité dédiée opaque `dv-<uuid>` ; une table
persistante conserve ce choix après retrait/réattribution d'un accès. Les comptes
natifs sont créés à la première connexion OIDC réussie, avec un mot de passe
aléatoire non communiqué et des droits ordinaires. Aucun compte existant n'est
fusionné par adresse e-mail. Les collisions d'identité bloquent la connexion.

- G1CRM : rôle `user`. Le CRM conserve son modèle de données partagées existant ;
  cette intégration ne crée pas une isolation des données par membre.
- G1Profil : rôle `user`, espace et modèles initiaux propres au nouveau compte.
- LiveMonitor : rôle `user`, statut `approved` ; droits natifs conservés.
- SentiNet : rôle `viewer`, écritures API refusées aux sessions SSO, car les
  routes de gestion existantes ne contrôlent pas systématiquement les rôles.
  Le module respecte l'étape MFA quand elle est activée ; une configuration MFA
  incomplète refuse la connexion.

## Sessions

Le connecteur vérifie le code OIDC, PKCE, état, nonce, signature RS256, audience,
identité UserInfo et association DevAntiq. Les paramètres temporaires restent
côté serveur, liés à un cookie hôte Secure/HttpOnly, expirent en cinq minutes
et ne sont utilisables qu'une fois. Les jetons natifs sont transmis au stockage
habituel des applications par une page sans cache à CSP nonce, jamais dans l'URL.

Les API vérifient la session DevAntiq courante pour chaque jeton natif issu du
SSO. Les WebSockets sont revérifiés toutes les quinze secondes. L'authentification
native existante reste en place ; ce connecteur ajoute des refus, pas une
acceptation fondée sur un JWT non vérifié. Une indisponibilité du service membres
refuse les requêtes des sessions SSO. G1Profil ne reçoit pas de refresh token
SSO natif : une nouvelle ouverture de la carte renouvelle sa session après huit
heures. Les autres modes de connexion natifs restent disponibles.

## Déploiement et reprise

Une erreur après écriture des sources désactive les nouveaux clients, restaure
les fichiers applicatifs sauvegardés et tente de redémarrer leurs services. La
mise à jour additive du portail reste installée ; aucune base complète n'est
restaurée automatiquement. Les dossiers d'adaptateurs sont conservés pour
diagnostic et une seconde installation nécessite un examen, sans écrasement
silencieux. Cloud et ses associations ne sont pas modifiés.

Après déploiement, tester les quatre cartes avec un membre autorisé puis le
retrait d'accès, le changement de membre et le compte local affiché. Vérifier
également les services applicatifs et les comptes natifs existants. Les tests
locaux ne remplacent pas cette recette.

## Futures applications

Réutiliser `connector.mjs` pour les applications Express compatibles ; fournir
un `resolveIdentity` qui vérifie le compte, conserve ses rôles et retourne sa
session native. Établir un adaptateur et des tests avant d'activer la création
de comptes. Ajouter ensuite la prise en charge à `NATIVE_APPS`, au déploiement,
à la passerelle et aux vérifications d'origine. Le seul ajout d'une carte ne
rend pas une application compatible SSO.

n8n Community conserve sa connexion interne. Umami, Zabbix et OmniRoute ne sont
pas couverts par ce paquet ; leur raccordement reste à réaliser séparément.
