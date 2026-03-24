/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts}'],
  theme: {
    extend: {
      colors: {
        // Dark theme palette (Komga-inspired)
        base: {
          DEFAULT: '#1e1e2e',
          surface: '#313244',
          overlay: '#45475a',
        },
        text: {
          DEFAULT: '#cdd6f4',
          muted: '#a6adc8',
          subtle: '#6c7086',
        },
        accent: {
          DEFAULT: '#89b4fa',
          hover: '#74c7ec',
        },
        error: '#f38ba8',
        success: '#a6e3a1',
        warning: '#fab387',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}

