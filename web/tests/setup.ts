/** Global setup for Vitest unit tests.
 *
 *  - jest-dom adds matchers like `toBeVisible()` / `toHaveTextContent()`.
 *  - i18next is initialized with the production resources so components that
 *    call `useTranslation()` resolve real strings instead of returning the
 *    raw key (which would break getByRole(name=...) matchers).
 */
import '@testing-library/jest-dom/vitest'
import '../src/i18n/config'
