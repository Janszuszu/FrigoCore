import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { apiAuth, setAuthToken, setUnauthorizedHandler } from "@/api";
import type { UserItem } from "@/types";

const TOKEN_KEY = "frigocore_token";

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY));
  const user = ref<UserItem | null>(null);
  const ready = ref(false);
  const error = ref<string | null>(null);

  setAuthToken(token.value);
  setUnauthorizedHandler(() => {
    if (token.value) logout();
  });

  const isAdmin = computed(() => user.value?.role === "admin");
  const isSerwisant = computed(() => user.value?.role === "serwisant");
  const isUser = computed(() => user.value?.role === "user");

  function setToken(next: string | null) {
    token.value = next;
    setAuthToken(next);
    if (next) localStorage.setItem(TOKEN_KEY, next);
    else localStorage.removeItem(TOKEN_KEY);
  }

  async function login(username: string, password: string) {
    error.value = null;
    try {
      const res = await apiAuth.login(username, password);
      setToken(res.access_token);
      user.value = res.user;
      return true;
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Logowanie nie powiodło się";
      return false;
    }
  }

  function logout() {
    setToken(null);
    user.value = null;
  }

  /** Restore a session from a stored token on app boot. */
  async function fetchMe() {
    if (!token.value) {
      ready.value = true;
      return;
    }
    try {
      user.value = await apiAuth.me();
    } catch {
      setToken(null);
      user.value = null;
    } finally {
      ready.value = true;
    }
  }

  return {
    token,
    user,
    ready,
    error,
    isAdmin,
    isSerwisant,
    isUser,
    login,
    logout,
    fetchMe,
  };
});
