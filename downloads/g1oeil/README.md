# Installateur G1Oeil

Version locale disponible : 1.0.0, construite le 9 août 2026.
Fichier : `G1Oeil-Setup-1.0.0.exe`, 106358548 octets.
Copié depuis `G1Oeil/url-monitor-live/release/G1Oeil Setup 1.0.0.exe`.
L'empreinte SHA-512 a été vérifiée contre le manifeste local `release/latest.yml` :

```text
nhvDmurozjVXsLjs15oZyfKhktINtPtQACeh54jcahvw8owq4US4aj5g1xStnjoTptgvTTu8NdBOfsrXeKOYCw==
```

Le fichier exécutable est exclu de Git et doit être transféré séparément sur le VPS.
Depuis PowerShell sur le PC :

```powershell
& 'E:\Mes-app\ProdApp\DevAntiq\scripts\deploy-g1oeil.ps1'
```

Le script demande le mot de passe SSH pour vérifier le site, transférer les fichiers,
puis vérifier leurs empreintes, sauvegarder la page et publier l'installateur avant
la page. Il ne redémarre aucun service et ne modifie que les fichiers G1Oeil.
Destination : `https://devantiq.com/g1oeil.html#telecharger`.

Cette version correspond au dernier installateur trouvé dans le projet local,
sans garantie d'intégration des changements de code ultérieurs à sa construction.
