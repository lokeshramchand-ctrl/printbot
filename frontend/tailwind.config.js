/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Premium gold accent scale — primary actions, active nav, focus
        // rings, and brand marks throughout the admin dashboard.
        gold: {
          50: '#FBF7EA',
          100: '#F5EBC8',
          200: '#EAD48F',
          300: '#DFBD63',
          400: '#D4AF37', // classic gold — icons, highlights
          500: '#C9A227', // primary interactive color
          600: '#AD8A1F', // hover / pressed
          700: '#8A6E19',
          800: '#665113',
          900: '#43350C',
          950: '#2A2107',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        display: ['"Playfair Display"', 'ui-serif', 'Georgia', 'serif'],
      },
      boxShadow: {
        gold: '0 8px 24px -8px rgba(201, 162, 39, 0.35)',
        'gold-sm': '0 2px 8px -2px rgba(201, 162, 39, 0.25)',
      },
    },
  },
  plugins: [],
}
