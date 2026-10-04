# DevAntiq — Site vitrine

Site web vitrine de **DevAntiq**, studio de création de logiciels, applications et expériences
numériques. Le site présente les services, l'agence et le portfolio d'applications, avec une page
détaillée par produit.

## Aperçu

- **Page d'accueil** (`index.html`) : hero animé, services, à propos, réalisations, méthode,
  témoignages et formulaire de contact.
- **Pages produits** : une landing par application du portfolio, avec contenu réel, carrousel
  d'images, lien vers le site officiel et appel à l'action.

## Structure du projet

```
.
├── index.html              # Page d'accueil
├── g1sport.html            # Page produit — G1Sport (coaching sportif)
├── g1club.html             # Page produit — G1Club (gestion de clubs sportifs)
├── g1oeil.html             # Page produit — G1Oeil (supervision d'URLs)
├── noteazy.html            # Page produit — Noteazy (station de travail tout-en-un)
├── css/
│   └── devantiq.css        # Styles partagés par les pages produits (+ carrousel)
├── img/                    # Logos et favicon
│   ├── devantiq-logo.png
│   ├── devantiq-icon.ico
│   ├── g1sport-logo.png
│   ├── g1club-logo.png
│   ├── g1oeil-logo.png
│   ├── noteazy-logo.png
│   └── noteazy-logo.ico
├── caroussel/              # Captures d'écran des applications
│   ├── g1sport/            # 13 images
│   ├── g1club/             # 8 images
│   ├── g1oeil/             # 6 images
│   └── noteazy/            # 9 images
├── .github/workflows/
│   └── deploy.yml          # Déploiement GitHub Pages
└── README.md
```

> La page d'accueil (`index.html`) embarque ses propres styles en ligne. Les pages produits
> partagent la feuille de style `css/devantiq.css`. Chaque page produit inclut un carrousel
> d'images auto-défilant (pause au survol) avec navigation par flèches et points.

## Technologies

- HTML5 / CSS3
- [Tailwind CSS](https://tailwindcss.com/) via CDN
- JavaScript natif (animation canvas, menu mobile, accordéon, carrousel, apparitions au scroll)
- Polices Google Fonts : *Syne* et *Space Grotesk*

Aucune étape de build n'est nécessaire : ce sont des pages statiques.

## Expérience visuelle

Les cinq pages chargent `css/experience.css` et `js/experience.js` : palette violet
profond, logos en lévitation, cartes avec perspective au pointeur et apparitions au scroll.
L'accueil présente une sphère de particules projetées en 3D sur Canvas, entourée de
liens vers les quatre applications. Aucun moteur 3D externe n'est nécessaire.

Le fond vidéo local `media/studio-aurora.mp4` est une boucle abstraite de huit secondes,
muette, avec une image de remplacement `media/studio-aurora.jpg`. La vidéo et le Canvas
s'arrêtent lorsque la scène quitte l'écran ou que l'onglet est masqué. La vidéo n'est
pas chargée automatiquement en mode économie de données ou réduction des animations.
Le bouton de pause arrête aussi les animations CSS et les carrousels produits ; son
choix est conservé pendant la session. Les carrousels restent utilisables manuellement.
Les effets de perspective suivent uniquement une souris ou un pointeur précis.

La vidéo est générée sans source externe avec FFmpeg ; pour la régénérer :
`powershell -File scripts/generate-aurora.ps1` (FFmpeg doit être installé).

## Lancer en local

Comme il s'agit de fichiers statiques, un simple serveur HTTP suffit :

```bash
# Python
python -m http.server 8000
```

Puis ouvrir <http://localhost:8000>.

## Réalisations & liens externes

| Application | Description | Site officiel |
|-------------|-------------|---------------|
| G1Sport | Plateforme de coaching sportif | https://g1sport.fr |
| G1Club | Gestion de clubs sportifs | https://g1club.fr |
| Noteazy | Station de travail tout-en-un | https://noteazy.com |
| G1Oeil | Supervision d'URLs en temps réel | *à venir* |

Le lien officiel de **G1Oeil** est déjà préparé (en commentaire) dans `g1oeil.html` et sur la carte
correspondante de `index.html` ; il suffira de l'activer une fois le site en ligne.

## Licence

© 2025 DevAntiq. Tous droits réservés. Projet propriétaire — usage interne à DevAntiq.
