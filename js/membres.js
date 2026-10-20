(() => {
  'use strict';
  const applications = [
    ['g1crm', 'G1CRM', 'Relation client', 'CR', '#a692ff'],
    ['g1profil', 'G1Profil', 'Profils, talents et recrutement', 'PR', '#67c7ee'],
    ['sentinet', 'SentiNet', 'Surveillance et sécurité du réseau', 'SN', '#68ddb4'],
    ['livemonitor', 'LiveMonitor', 'Supervision en direct', 'LM', '#ef93ac'],
    ['umami', 'Umami', 'Statistiques de fréquentation', 'UM', '#c0b4fa'],
    ['cloud', 'Cloud', 'Vos fichiers, réunis et accessibles', 'CL', '#7aaef6'],
    ['n8n', 'n8n', 'Automatisation de vos workflows', 'n8', '#f49e89'],
    ['omniroute', 'OmniRoute', 'Votre espace OmniRoute', 'OR', '#e1b76a'],
    ['zabbix', 'Zabbix', 'Supervision de l’infrastructure', 'ZA', '#f08494'],
  ];
  const presentations = {
    g1crm: 'Gérez vos contacts, vos opportunités commerciales, vos devis et vos factures dans un même espace. Suivez vos échanges et vos rendez-vous pour faire avancer chaque relation client.',
    g1profil: 'Trouvez les bons talents et suivez vos recrutements, du sourcing à l’embauche. Centralisez les CV, organisez les candidatures et planifiez vos entretiens.',
    sentinet: 'Gardez une vue d’ensemble de la sécurité de votre réseau. Consultez les informations de surveillance pour repérer les événements qui nécessitent votre attention.',
    livemonitor: 'Suivez l’état de vos services et de vos serveurs en direct. Rassemblez vos indicateurs de supervision pour identifier les incidents et prioriser vos interventions.',
    umami: 'Comprenez comment vos visiteurs utilisent vos sites web. Consultez la fréquentation, les pages visitées et les sources de trafic pour mesurer votre audience.',
    cloud: 'Retrouvez, organisez et partagez vos fichiers depuis votre espace en ligne. Gardez vos documents à portée de main pour travailler et collaborer au quotidien.',
    n8n: 'Reliez vos applications et automatisez vos tâches répétitives. Construisez des workflows visuels pour faire circuler les données et simplifier vos processus.',
    omniroute: 'Centralisez vos connexions aux fournisseurs d’intelligence artificielle. Pilotez le routage des requêtes et consultez les indicateurs d’utilisation et de coûts.',
    zabbix: 'Surveillez la disponibilité et les performances de votre infrastructure. Consultez les métriques de vos équipements et les alertes pour suivre leur état de santé.',
  };
  let catalog = applications;
  const grid = document.getElementById('applications');
  const status = document.getElementById('session-status');
  const login = document.getElementById('login');
  const account = document.getElementById('account');
  const retry = document.getElementById('retry');
  const search = document.getElementById('search');
  let state = 'loading';
  let grants = new Map();
  let onlyMine = false;
  let checkId = 0;
  function render() {
    grid.replaceChildren();
    const query = search.value.trim().toLocaleLowerCase('fr');
    const filtered = catalog.filter(app => `${app.join(' ')} ${presentations[app[0]] || ''}`.toLocaleLowerCase('fr').includes(query)
      && (!onlyMine || grants.get(app[0])?.allowed));
    document.getElementById('empty').hidden = filtered.length !== 0;
    filtered.forEach(([id, name, description, initials, color]) => {
      const card = document.createElement('article');
      card.className = 'app-card';
      card.style.setProperty('--color', color);
      const visual = document.createElement('div'); visual.className = 'app-visual';
      const background = document.createElement('img');
      background.className = 'app-scene'; background.src = `img/members/${id}-landing.png`;
      background.alt = ''; background.loading = 'lazy'; background.width = 640; background.height = 360;
      background.addEventListener('error', () => {
        if (!background.dataset.fallback) {
          background.dataset.fallback = '1'; background.src = `img/members/${id}-scene.svg`;
        } else { background.hidden = true; }
      });
      const icon = document.createElement('span');
      icon.className = `app-icon app-icon-${id}`;
      const logo = document.createElement('img');
      logo.src = `img/members/${id}.${['g1crm', 'livemonitor'].includes(id) ? 'png' : 'svg'}`;
      logo.alt = ''; logo.width = 64; logo.height = 64;
      logo.addEventListener('error', () => { icon.textContent = initials; });
      icon.append(logo);
      icon.style.setProperty('--color', color); icon.setAttribute('aria-hidden', 'true');
      visual.append(background, icon);
      const title = document.createElement('h3'); title.textContent = name;
      const copy = document.createElement('p'); copy.className = 'app-description';
      copy.textContent = presentations[id] || description;
      const domain = document.createElement('p'); domain.className = 'domain'; domain.textContent = `${id}.devantiq.com`;
      const grant = grants.get(id);
      const authorized = state === 'authenticated' && grant?.allowed === true && grant?.enabled === true;
      const badge = document.createElement('span'); badge.className = 'access-badge';
      badge.textContent = authorized ? 'Accès autorisé' : state === 'authenticated' && grant?.allowed ? 'Activation en cours' : 'Accès sur attribution';
      const action = document.createElement(authorized ? 'a' : 'span');
      if (authorized) {
        // Keep compatibility with the deployed portal while native adapters roll out.
        const direct = `https://${id}.devantiq.com`;
        action.href = grant.url === direct || grant.url === `${direct}/`
          ? `${direct}/` : `/auth/apps/${id}/open/`;
        action.target = '_blank'; action.rel = 'noopener noreferrer';
        action.textContent = `Ouvrir ${name} ↗`;
      } else {
        action.className = 'locked';
        action.textContent = state === 'anonymous' ? 'Connexion requise' : state === 'loading' ? 'Vérification…' : state === 'authenticated' ? (grant?.allowed ? 'Disponible après activation' : 'Non attribué à votre compte') : 'Accès indisponible';
      }
      card.append(visual, badge, title, copy, domain, action);
      grid.append(card);
    });
  }
  async function checkSession() {
    const currentCheck = ++checkId;
    grants = new Map();
    catalog = applications;
    state = 'loading'; login.hidden = account.hidden = retry.hidden = true;
    document.getElementById('admin').hidden = document.getElementById('logout').hidden = true;
    document.getElementById('filter-mine').disabled = true;
    status.textContent = 'Vérification de votre connexion…'; render();
    try {
      const response = await fetch('/api/member-session', { credentials: 'same-origin', cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(10000) });
      if (currentCheck !== checkId) return;
      // A static hosting fallback returning HTML/200 must never unlock the portal.
      if (response.status === 200 && response.headers.get('X-DevAntiq-Session') === 'authenticated') {
        const session = await response.json();
        if (currentCheck !== checkId) return;
        if (!session.user || typeof session.user.name !== 'string' || typeof session.csrf !== 'string'
            || !Array.isArray(session.applications)) throw new Error('Session invalide');
        const registered = session.applications.filter(app => typeof app.id === 'string'
          && /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(app.id)
          && typeof app.name === 'string' && typeof app.description === 'string');
        grants = new Map(registered.map(app => [app.id, app]));
        catalog = [...grants.values()].map(app => {
          const known = applications.find(item => item[0] === app.id);
          return [app.id, app.name, app.description, known?.[3] || app.name.slice(0, 2).toUpperCase(), known?.[4] || '#a692ff'];
        });
        state = 'authenticated'; account.hidden = false;
        status.textContent = `Bonjour ${session.user.name}. Retrouvez ci-dessous les accès attribués par votre administrateur.`;
        document.getElementById('admin').hidden = session.user.is_admin !== true;
        document.getElementById('csrf-token').value = session.csrf;
        document.getElementById('logout').hidden = false;
        document.getElementById('filter-mine').disabled = false;
        const count = [...grants.values()].filter(app => app.allowed === true && app.enabled === true).length;
        document.getElementById('access-count').textContent = `${count} accès actif${count > 1 ? 's' : ''} · ${catalog.length} applications`;
        document.getElementById('catalog-note').textContent = count ? 'Vos accès sont vérifiés à chaque ouverture. Une connexion propre à l’application peut également être demandée.' : 'Aucun accès actif pour le moment. Votre administrateur peut vous attribuer des applications.';
      } else if (response.status === 401) {
        state = 'anonymous'; login.hidden = false;
        status.textContent = 'Connectez-vous avec votre compte DevAntiq pour accéder à vos applications.';
      } else if (response.status === 403) {
        state = 'denied'; account.hidden = false;
        status.textContent = 'Votre compte ne dispose pas de l’accès membre. Contactez le studio pour demander son activation.';
      } else { throw new Error('Service indisponible'); }
    } catch {
      if (currentCheck !== checkId) return;
      state = 'unavailable'; retry.hidden = false;
      status.textContent = 'La connexion est momentanément indisponible. Réessayez plus tard ou contactez le studio.';
    }
    if (state !== 'authenticated') {
      onlyMine = false;
      document.getElementById('filter-all').setAttribute('aria-pressed', 'true');
      document.getElementById('filter-mine').setAttribute('aria-pressed', 'false');
      document.getElementById('access-count').textContent = '9 applications';
      document.getElementById('catalog-note').textContent = 'Connectez-vous pour ouvrir les applications autorisées pour votre compte.';
    }
    render();
  }
  ['all', 'mine'].forEach(filter => document.getElementById(`filter-${filter}`).addEventListener('click', () => {
    onlyMine = filter === 'mine' && state === 'authenticated';
    document.getElementById('filter-all').setAttribute('aria-pressed', String(!onlyMine));
    document.getElementById('filter-mine').setAttribute('aria-pressed', String(onlyMine));
    render();
  }));
  search.addEventListener('input', render);
  retry.addEventListener('click', checkSession);
  window.addEventListener('pageshow', checkSession);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) checkSession(); });
})();
