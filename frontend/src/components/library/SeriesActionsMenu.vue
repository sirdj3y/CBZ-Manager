<script setup>
// Menu "⋯" d'une série (cartes de la grille Séries et des rangées de l'accueil). Le bouton
// déclencheur est fourni par le parent (slot), pour garder ses styles de survol. Menu non
// modal : un clic ailleurs le ferme ET agit (ex. ouvrir directement le menu d'une autre
// carte). Position, débordement d'écran et navigation clavier gérés par Reka UI — plus de
// calcul de position à la main pour échapper au défilement horizontal des rangées.
import { useAuthStore } from '../../stores/auth'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/shadcn/dropdown-menu'

defineProps({ series: { type: Object, required: true } })
const open = defineModel('open', { type: Boolean, default: false })
defineEmits(['edit', 'enrich', 'rename', 'convert', 'download', 'set-cover', 'toggle-hidden', 'delete'])
const authStore = useAuthStore()
</script>

<template>
  <DropdownMenu v-model:open="open" :modal="false">
    <DropdownMenuTrigger as-child>
      <slot />
    </DropdownMenuTrigger>
    <DropdownMenuContent align="start" class="min-w-[190px]">
      <template v-if="authStore.hasPermission('library.metadata_edit')">
        <DropdownMenuItem @select="$emit('edit', series)">Éditer les métadonnées</DropdownMenuItem>
        <DropdownMenuItem @select="$emit('enrich', series)">Compléter les métadonnées</DropdownMenuItem>
      </template>
      <DropdownMenuItem v-if="authStore.hasPermission('library.rename')" @select="$emit('rename', series)">Renommer les fichiers</DropdownMenuItem>
      <DropdownMenuItem v-if="authStore.hasPermission('library.convert')" @select="$emit('convert', series)">Convertir les fichiers</DropdownMenuItem>
      <DropdownMenuItem v-if="authStore.hasPermission('library.download')" @select="$emit('download', series)">Télécharger la série</DropdownMenuItem>
      <DropdownMenuItem v-if="authStore.hasPermission('library.metadata_edit')" @select="$emit('set-cover', series)">Modifier la miniature</DropdownMenuItem>
      <DropdownMenuSeparator v-if="authStore.hasPermission('library.metadata_edit') || authStore.hasPermission('library.delete')" />
      <DropdownMenuItem v-if="authStore.hasPermission('library.metadata_edit')" @select="$emit('toggle-hidden', series)">
        {{ series.hidden ? 'Afficher la série' : 'Masquer la série' }}
      </DropdownMenuItem>
      <DropdownMenuItem v-if="authStore.hasPermission('library.delete')" variant="destructive" @select="$emit('delete', series)">
        Supprimer la série
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
