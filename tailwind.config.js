/** @type {import("tailwindcss").Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",
    "./app/**/*.py"  // This will also catch any classes in Python files
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
