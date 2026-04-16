/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#6366f1',
          dark: '#4f46e5',
        },
        dark: {
          bg: '#0f172a',
          card: '#1e293b',
          hover: '#334155',
          border: '#334155',
        },
      },
    },
  },
  plugins: [],
}
