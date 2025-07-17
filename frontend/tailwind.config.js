/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  // Add the typography plugin here
  plugins: [
    require('@tailwindcss/typography'),
  ],
}
