# Installateur Noteazy

La page `noteazy.html#telecharger` utilise le fichier `NotEazy-Setup-1.0.37.exe`.
L'installateur Windows est copié depuis le dossier `release` du projet local NotEazy.
Taille attendue : 257246264 octets. Le binaire est exclu de Git.

Vérification du 17 octobre 2026 : le manifeste public
`https://noteazy.com/downloads/latest.yml` annonce la version 1.0.37,
publiée le 19 août 2026 à 23:45 UTC. L'empreinte SHA-512 du fichier local
correspond à celle du manifeste :

```text
z3PlceHjPNv8JwG9C2msj7eGsgLCPWLpUBDZ51iEI0vw7nhEnfsL66b9AWG1sjLJEv+h2SxjcmCUldCqdY/nqQ==
```

## Déploiement

Transférer le binaire **avant** de déployer la page qui contient son lien. Un simple
`git pull` ne transfère pas l'installateur.

Depuis PowerShell, à la racine du projet (remplacer `utilisateur@vps`) :

```powershell
ssh utilisateur@vps 'mkdir -p /var/www/devantiq/downloads/noteazy'
scp ./downloads/noteazy/NotEazy-Setup-1.0.37.exe utilisateur@vps:/var/www/devantiq/downloads/noteazy/NotEazy-Setup-1.0.37.exe.part
ssh utilisateur@vps 'test "$(stat -c %s /var/www/devantiq/downloads/noteazy/NotEazy-Setup-1.0.37.exe.part)" = 257246264 && chmod 644 /var/www/devantiq/downloads/noteazy/NotEazy-Setup-1.0.37.exe.part && mv /var/www/devantiq/downloads/noteazy/NotEazy-Setup-1.0.37.exe.part /var/www/devantiq/downloads/noteazy/NotEazy-Setup-1.0.37.exe'
```

Après transfert, vérifier que l'URL
`https://devantiq.com/downloads/noteazy/NotEazy-Setup-1.0.37.exe` répond correctement,
puis déployer `noteazy.html`. Aucun redémarrage des autres applications du VPS n'est nécessaire pour ces fichiers statiques.
