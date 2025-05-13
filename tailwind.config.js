/** @type {import('tailwindcss').Config} */
module.exports = {
    content: [
      "./src/templates/**/*.html",
      "./src/static/js/**/*.js"  
    ],
    
    darkMode: 'class', // 'media' or 'class'
    
    theme: {
      extend: {
        colors: {
          primary: {
            50: '#f0fdf4',
            100: '#dcfce7',
            200: '#bbf7d0',
            300: '#86efac',
            400: '#4ade80',
            500: '#22c55e',
            600: '#16a34a',
            700: '#15803d',
            800: '#166534',
            900: '#14532d',
            950: '#052e16',
          }
        },
        fontSize: {
          'xs': ['0.75rem', { lineHeight: '1rem' }],
          'sm': ['0.875rem', { lineHeight: '1.25rem' }],
          'base': ['1rem', { lineHeight: '1.5rem' }],
          'lg': ['1.125rem', { lineHeight: '1.75rem' }],
          'xl': ['1.25rem', { lineHeight: '1.75rem' }],
          '2xl': ['1.5rem', { lineHeight: '2rem' }],
          '3xl': ['1.875rem', { lineHeight: '2.25rem' }],
          '4xl': ['2.25rem', { lineHeight: '2.5rem' }],
        },
        boxShadow: {
          'card': '0 2px 8px rgba(0, 0, 0, 0.1)',
        },
        animation: {
          'spin-slow': 'spin 3s linear infinite',
        }
      }
    },
    
    plugins: [
        require('@tailwindcss/line-clamp'),

    ],
  }