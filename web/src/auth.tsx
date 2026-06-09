import { createContext, useContext, type ReactNode } from 'react'
import type { AuthPrincipal, AuthRole, AuthState } from './api'

const ROLE_ORDER: Record<AuthRole, number> = {
  viewer: 0,
  editor: 1,
  admin: 2,
}

export function hasRoleAtLeast(role: AuthRole | null | undefined, required: AuthRole): boolean {
  if (!role) return false
  return ROLE_ORDER[role] >= ROLE_ORDER[required]
}

export function canWrite(principal: AuthPrincipal | null | undefined): boolean {
  if (!principal) return true
  return hasRoleAtLeast(principal.role, 'editor')
}

export function canDelete(principal: AuthPrincipal | null | undefined): boolean {
  return hasRoleAtLeast(principal?.role, 'admin')
}

export function isAdmin(principal: AuthPrincipal | null | undefined): boolean {
  return canDelete(principal)
}

export interface AuthContextValue {
  auth: AuthState | null
  loading: boolean
  refreshAuth: () => Promise<void>
  signInWithToken: (token: string) => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({
  value,
  children,
}: {
  value: AuthContextValue
  children: ReactNode
}) {
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}

export function useAuthMaybe(): AuthContextValue | null {
  return useContext(AuthContext)
}
