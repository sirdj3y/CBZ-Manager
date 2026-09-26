<script setup>
// Menu "⋯" d'un album (grilles de la fiche Série et de la page Albums). Même principe que
// SeriesActionsMenu : déclencheur fourni par le parent (slot), menu non modal, position gérée
// par Reka UI.
import { tomesApi } from '../../api/tomes'
import { useAuthStore } from '../../stores/auth'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/shadcn/dropdown-menu'

defineProps({ tome: { type: Object, required: true } })
const open = defineModel('open', { type: Boolean, default: false })
defineEmits(['edit', 'search-metadata', 'move', 'delete'])
const authStore = useAuthStore()
</script>

<template>
  <DropdownMenu v-model:open="open" :modal="false">
    <DropdownMenuTrigger as-child>
      <slot />
    </DropdownMenuTrigger>
    <DropdownMenuContent align="start" class="min-w-[190px]">
      <template v-if="authStore.hasPermission('library.metadata_edit')">
        <DropdownMenuItem @select="$emit('edit', tome)">Éditer les métadonnées</DropdownMenuItem>
        <DropdownMenuItem @select="$emit('search-metadata', tome)">Rechercher les métadonnées</DropdownMenuItem>
      </template>
      <DropdownMenuItem v-if="authStore.hasPermission('library.move')" @select="$emit('move', tome)">Déplacer vers une série</DropdownMenuItem>
      <DropdownMenuItem v-if="authStore.hasPermission('library.download')" as-child>
        <!-- Neutralise le style global des liens (style.css : couleur vermillon, souligné au survol). -->
        <a :href="tomesApi.downloadUrl(tome.id)" class="text-foreground no-underline hover:no-underline">Télécharger</a>
      </DropdownMenuItem>
      <template v-if="authStore.hasPermission('library.delete')">
        <DropdownMenuSeparator />
        <DropdownMenuItem variant="destructive" @select="$emit('delete', tome)">Supprimer l'album</DropdownMenuItem>
      </template>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
