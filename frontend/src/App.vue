<script setup>
import Notification from './components/layout/Notification.vue'
import { TooltipProvider } from '@/components/shadcn/tooltip'
</script>

<template>
  <!-- Réglage commun des infobulles (components/ui/Hint.vue) : délai avant apparition, et
       passage instantané d'une infobulle à la voisine quand on survole une rangée de boutons ;
       au focus, seulement depuis le clavier (sinon chaque clic afficherait l'infobulle). -->
  <TooltipProvider :delay-duration="400" :skip-delay-duration="300" ignore-non-keyboard-focus>
    <router-view />
    <Notification />
  </TooltipProvider>
</template>
