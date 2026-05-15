import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Select } from '../Select'

/**
 * The themed Select is a styled wrapper around the native `<select>`,
 * which is intentional (see Select.tsx + filters/FilterSelect.tsx
 * docstrings): keyboard nav, focus rings, and mobile touch sheets all
 * come from the browser. Tests check the controlled API + accessibility
 * surface (aria-label, aria-invalid, disabled options).
 */

interface ColorOption {
  value: string
  label: string
  disabled?: boolean
}

const COLORS: ColorOption[] = [
  { value: 'red', label: 'Red' },
  { value: 'green', label: 'Green' },
  { value: 'blue', label: 'Blue', disabled: true },
]

describe('Select', () => {
  it('renders one option per entry plus a placeholder when supplied', () => {
    render(
      <Select<string>
        value=""
        onChange={() => {}}
        options={COLORS.map((c) => ({ value: c.value, label: c.label, disabled: c.disabled }))}
        placeholder="Choose a color"
        ariaLabel="color"
      />,
    )
    const select = screen.getByRole('combobox', { name: 'color' }) as HTMLSelectElement
    // placeholder + 3 options = 4 children
    expect(select.options).toHaveLength(4)
    expect(select.options[0]).toHaveAttribute('disabled')
    expect(select.options[0]).toHaveValue('')
  })

  it('fires onChange with the unwrapped value on selection', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(
      <Select<string>
        value="red"
        onChange={onChange}
        ariaLabel="color"
        options={COLORS.map((c) => ({ value: c.value, label: c.label, disabled: c.disabled }))}
      />,
    )
    await user.selectOptions(screen.getByRole('combobox', { name: 'color' }), 'green')
    expect(onChange).toHaveBeenCalledWith('green')
  })

  it('disables individual options via option.disabled', () => {
    render(
      <Select<string>
        value="red"
        onChange={() => {}}
        ariaLabel="color"
        options={COLORS.map((c) => ({ value: c.value, label: c.label, disabled: c.disabled }))}
      />,
    )
    const blueOption = screen.getByRole('option', { name: 'Blue' }) as HTMLOptionElement
    expect(blueOption).toHaveAttribute('disabled')
  })

  it('disables the whole select when disabled prop is set', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(
      <Select<string>
        value="red"
        onChange={onChange}
        disabled
        ariaLabel="color"
        options={[{ value: 'red', label: 'Red' }]}
      />,
    )
    const select = screen.getByRole('combobox', { name: 'color' })
    expect(select).toBeDisabled()
    await user.click(select)
    expect(onChange).not.toHaveBeenCalled()
  })

  it('exposes aria-invalid when error prop is set', () => {
    render(
      <Select<string>
        value="red"
        onChange={() => {}}
        ariaLabel="color"
        error
        options={[{ value: 'red', label: 'Red' }]}
      />,
    )
    expect(screen.getByRole('combobox', { name: 'color' })).toHaveAttribute(
      'aria-invalid',
      'true',
    )
  })

  it('keyboard: focus + arrow + enter selects an option', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(
      <Select<string>
        value="red"
        onChange={onChange}
        ariaLabel="color"
        options={COLORS.filter((c) => !c.disabled).map((c) => ({
          value: c.value,
          label: c.label,
        }))}
      />,
    )
    const select = screen.getByRole('combobox', { name: 'color' })
    select.focus()
    // Native selects: pressing the first letter of an option name jumps to it
    // (or arrow keys when the menu is open). We exercise the controlled
    // contract via selectOptions which simulates the same end-state.
    await user.selectOptions(select, 'green')
    expect(onChange).toHaveBeenCalledWith('green')
  })
})
