/**
 * One focused failure-path test — **real backend rejection, no interception**.
 *
 * A CSV below the documented minimum row count is rejected by the real API
 * (HTTP 422 with a structured message) and the UI must show an understandable
 * error; the user must then be able to clear it and carry on using the app.
 *
 * The 422 is registered with `allowFailure` so it is recorded as an intentional
 * failure in the diagnostics instead of being silently filtered or reported as a
 * bug.
 */
import { expect, test } from './fixtures'

const TOO_SMALL_CSV = ['customer_id,amount,split', 'C-1,3,train', 'C-2,5,test', 'C-3,7,train'].join('\n')

test('rejected upload shows an understandable error and the user can recover', async ({
  page,
  allowFailure,
}) => {
  allowFailure(/HTTP 422 .*\/api\/datasets/)

  await page.goto('/#/overview')
  await expect(page.getByRole('navigation', { name: 'Primary' })).toBeVisible()

  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: /Data/ }).click()
  await expect(page.getByRole('heading', { name: 'Load a dataset' })).toBeVisible()

  // Rejecting request: 3 rows is below the documented minimum of 20.
  await page.locator('input[type="file"]').setInputFiles({
    name: 'too_small.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(TOO_SMALL_CSV),
  })

  // The error must be understandable: the app shows both a global error alert and
  // a dataset-view "Upload rejected" callout carrying the backend's message.
  const uploadAlert = page.getByRole('alert').filter({ hasText: 'Upload rejected' })
  await expect(uploadAlert).toBeVisible()
  await expect(uploadAlert).toContainText('validation_error')
  await expect(uploadAlert).toContainText('at least 20 are required')
  await expect(page.getByRole('alert').filter({ hasText: 'Something went wrong' })).toBeVisible()
  const details = page.locator('details').filter({ hasText: 'Technical details' })
  await expect(details).toContainText('rows_found')
  await expect(details).toContainText('rows_required')

  // No dataset was loaded by the rejected request.
  await expect(page.getByText('No dataset is loaded')).toBeVisible()

  // Recovery: dismiss the error and use the app normally.
  await page.getByRole('button', { name: 'Dismiss' }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)

  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: /Start/ }).click()
  await page
    .locator('.we__demo')
    .filter({ hasText: 'Repeated-entity subscription panel' })
    .getByRole('button', { name: 'Open', exact: true })
    .click()

  await expect(page).toHaveURL(/#\/dataset$/)
  await expect(page.getByRole('combobox', { name: 'Entity column' })).toHaveValue('customer_id')
  await expect(page.getByText('repeated_entity.csv')).toBeVisible()
})
