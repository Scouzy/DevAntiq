# Routage observé sur le VPS

Source : inspection transmise par le propriétaire le 18 octobre 2026.
Ce relevé permet de préparer l'intégration ; aucune des protections ci-dessous
n'a encore été activée sur le serveur.

| Configuration actuelle | Hôte | Emplacements à prendre en compte |
|---|---|---|
| `/etc/nginx/sites-enabled/devantiq` | `devantiq.com`, `www.devantiq.com` | Ajouter `portal.conf` dans le serveur HTTPS du site, sans modifier l'API contact existante. Ce même fichier contient aussi les serveurs G1CRM. |
| `/etc/nginx/sites-enabled/devantiq` | `g1crm.devantiq.com` | `/api/`, `/assets/`, `/` et le repli `/index.html`. |
| `/etc/nginx/sites-enabled/g1crm` | `crm.devantiq.com` | Alias HTTP : rediriger vers `https://g1crm.devantiq.com$request_uri` au lieu de servir une seconde origine sans protection. |
| `/etc/nginx/sites-enabled/g1profil.devantiq.com` | `g1profil.devantiq.com` | `/api/auth/`, `/api/`, `/assets/`, `/index.html`, `/`. Préserver le challenge ACME public. |
| `/etc/nginx/sites-enabled/sentinet.devantiq.com` | `sentinet.devantiq.com` | `/`, `/assets/`, `/api/`, `/ws`. |
| `/etc/nginx/sites-enabled/livemonitor` | `livemonitor.devantiq.com` | `/`, `/api/`, `/ws`, `/agent/`, `/agent-noteazy/`, `/agent-g1sport/`, `/agent-g1club/`, `/agent-g1tournoi/`. |
| `/etc/nginx/sites-enabled/livemonitor-admin` | `admin.livemonitor.devantiq.com` | `/` : accès d'administration distinct, refusé par défaut. Ne pas l'ouvrir à tous les membres LiveMonitor. |
| `/etc/nginx/conf.d/umami.conf` | `umami.devantiq.com` | `/` ; isoler les routes exactes du script et de collecte après vérification de la version en service. |
| `/etc/nginx/conf.d/nextcloud.conf` | `cloud.devantiq.com` | `/` ; Nextcloud 29. Vérifier les clients WebDAV et le raccordement SSO avant d'imposer une connexion interactive. |
| `/etc/nginx/sites-enabled/n8n` | `n8n.devantiq.com` | `/` ; identifier les webhooks actifs et les retours OAuth avant changement. |
| `/etc/nginx/sites-enabled/omniroute` | `omniroute.devantiq.com` | `/` ; identifier les appels API automatisés avant changement. |
| `/etc/nginx/conf.d/zabbix.conf` | `zabbix.devantiq.com` | `/`, `/assets`, `/favicon.ico`, `/metrics` et surtout le bloc PHP/FastCGI. Préserver les refus existants sur les fichiers internes. |

Installer `auth-location.conf` dans chaque serveur applicatif HTTPS concerné et
`require-member.conf` dans ses emplacements accessibles. Pour Zabbix, vérifier
l'autorisation **dans le bloc PHP également** : protéger uniquement `/` laisse
les appels directs aux scripts PHP hors du contrôle d'accès.

Ne pas remplacer globalement tous les blocs `server` du fichier `devantiq` :
cela affecterait aussi G1CRM. Les redirections HTTP existantes restent publiques ;
le contenu applicatif doit être servi exclusivement par les hôtes HTTPS protégés.

La liste des routes ne suffit pas à déterminer quels clients machines utilisent
les agents, les métriques, les webhooks ou WebDAV. Aucun de ces chemins n'est
exempté automatiquement de l'authentification. Les exemptions éventuelles sont
conditionnées à la présence vérifiée d'un contrôle d'accès propre au service.
