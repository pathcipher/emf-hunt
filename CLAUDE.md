# EMF Hunt

This is a mobile webapp for a puzzle hunt at EMF Camp 2026. The most important things in this project are:

- Mobile accessibility. Everything should render well on mobile devices. Laptop screens are a secondary concern
- Security. The site should not have any injection opportunities. All code in the repo should be able to be made public without exposing puzzle or personal details.
- Zero-trust. No user passwords are to be stored. Login should be via magic link.
- Strict progression. Users should get one puzzle at a time to work on, and should not have access to future puzzles before completing the last.
- Admin pages. There should be an option of marking a user as an admin (first user automatically gets admin). Admins can edit puzzle pages (html-based editor within the site theme) and answers, and see team progression.


