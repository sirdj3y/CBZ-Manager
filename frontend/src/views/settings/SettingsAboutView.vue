<script setup>
import { ref, onMounted } from 'vue'
import AppLayout from '../../components/layout/AppLayout.vue'
import { settingsApi } from '../../api/settings'

const about = ref(null)
const appVersion = __APP_VERSION__

onMounted(async () => {
  const { data } = await settingsApi.about()
  about.value = data
})

function fmtSize(bytes) {
  if (!bytes) return '0 Mo'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + ' Ko'
  if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' Mo'
  return (bytes / 1024 / 1024 / 1024).toFixed(2) + ' Go'
}
</script>

<template>
  <AppLayout>
    <main class="settings-main">
      <h1 class="settings-heading">À propos</h1>

      <!-- Description -->
      <section class="card settings-section">
        <div class="card-body">
          <p class="about-tagline">CBZ Manager est une interface web qui permet de gérer, enrichir et lire une bibliothèque de BD et comics.</p>
          <p class="about-desc">Organisez votre bibliothèque de façon structurée et élégante. L'app permet l'import, la conversion, le renommage, l'édition de métadonnées et la lecture dans une seule interface fluide. Elle automatise les tâches chronophages (organisation, tagging, compression) tout en laissant un contrôle fin à l'utilisateur, le tout sans dépendance cloud.</p>
        </div>
      </section>

      <!-- Auteur -->
      <section class="card settings-section">
        <div class="card-body">
          <div class="settings-section-title">Auteur</div>
          <div class="author-block">
            <div class="author-avatar">S</div>
            <div class="author-info">
              <div class="author-name">sirdj3y</div>
              <div class="author-desc">Développeur de CBZManager. Qui est-il ? D'où vient-il ?</div>
            </div>
          </div>
        </div>
      </section>

      <!-- Application -->
      <section class="card settings-section">
        <div class="card-body">
          <div class="settings-section-title">Application</div>
          <div class="about-infos">
            <div class="about-info-row">
              <span class="about-info-label">Version</span>
              <span class="about-info-value"><code>v{{ appVersion }}</code></span>
            </div>
            <div class="about-info-row">
              <span class="about-info-label">Base de données</span>
              <span class="about-info-value">SQLite</span>
            </div>
            <div class="about-info-row">
              <span class="about-info-label">Cache covers</span>
              <span class="about-info-value">{{ fmtSize(about?.cover_cache_size) }}</span>
            </div>
            <div class="about-info-row">
              <span class="about-info-label">Stack</span>
              <span class="about-info-value">Vue 3 · FastAPI · Docker</span>
            </div>
          </div>
        </div>
      </section>

    </main>
  </AppLayout>
</template>

<style scoped>
.settings-main {
  flex: 1; padding: 24px 20px;
  max-width: 680px; margin: 0 auto; width: 100%;
}
.settings-heading {
  font-size: 1.4rem; font-weight: 700;
  margin-bottom: 20px; color: var(--text);
}
.settings-section { margin-bottom: 16px; }
.settings-section-title {
  font-size: 0.8rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.05em; color: var(--muted); margin-bottom: 14px;
}

.author-block {
  display: flex; align-items: center; gap: 14px;
}
.author-avatar {
  width: 44px; height: 44px; border-radius: 50%;
  background: var(--primary); color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 1.2rem; font-weight: 700; flex-shrink: 0;
}
.author-name { font-weight: 600; font-size: 0.95rem; color: var(--text); margin-bottom: 2px; }
.author-desc { font-size: 0.8rem; color: var(--muted); }

.about-tagline { font-size: 0.95rem; font-weight: 600; color: var(--text); margin-bottom: 8px; }
.about-desc { font-size: 0.85rem; color: var(--muted); line-height: 1.6; }

.about-infos {
  border: 1px solid var(--border); border-radius: var(--radius-sm); overflow: hidden;
}
.about-info-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 7px 12px; font-size: 0.82rem;
  border-bottom: 1px solid var(--border);
}
.about-info-row:last-child { border-bottom: none; }
.about-info-label { color: var(--muted); }
.about-info-value { font-weight: 500; color: var(--text); }
.about-info-value code { font-size: 0.82rem; background: var(--light); padding: 1px 6px; border-radius: 4px; }
</style>
