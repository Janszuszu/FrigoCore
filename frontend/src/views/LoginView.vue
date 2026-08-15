<script setup lang="ts">
import { ref } from "vue";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();
const username = ref("");
const password = ref("");
const submitting = ref(false);

async function submit() {
  if (!username.value || !password.value) return;
  submitting.value = true;
  await authStore.login(username.value, password.value);
  submitting.value = false;
}
</script>

<template>
  <div class="login-shell">
    <form class="login-card" @submit.prevent="submit">
      <div class="brand">
        <svg viewBox="0 0 24 24"><path d="m12 2 8 4.5v11L12 22l-8-4.5v-11L12 2Z"/><path d="m4 6.5 8 4.5 8-4.5M12 11v11" /></svg>
        <span>FRIGO CORE</span>
      </div>
      <label class="field">
        <span>Nazwa użytkownika</span>
        <input v-model="username" autocomplete="username" autofocus />
      </label>
      <label class="field">
        <span>Hasło</span>
        <input v-model="password" type="password" autocomplete="current-password" />
      </label>
      <p v-if="authStore.error" class="error">{{ authStore.error }}</p>
      <button type="submit" class="submit" :disabled="submitting || !username || !password">
        {{ submitting ? "Logowanie…" : "Zaloguj się" }}
      </button>
    </form>
  </div>
</template>

<style scoped>
.login-shell {
  height: 100vh;
  display: grid;
  place-items: center;
  background: #020910;
  color: #edf4ff;
}

.login-card {
  width: min(340px, 90vw);
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 32px 28px;
  background: #08151f;
  border: 1px solid #1d3b53;
  border-radius: 12px;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.55);
}

.brand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: #12e5e6;
  font-size: 19px;
  letter-spacing: 1px;
  font-weight: 600;
  margin-bottom: 8px;
}

.brand svg {
  width: 26px;
  height: 30px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.field {
  display: block;
}

.field > span {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  color: #a9bdd8;
}

.field input {
  width: 100%;
  box-sizing: border-box;
  background: #050f1a;
  border: 1px solid #234662;
  border-radius: 6px;
  color: #f1f6ff;
  padding: 10px 12px;
  font: inherit;
  font-size: 14px;
}

.field input:focus {
  outline: none;
  border-color: #00b6d6;
}

.error {
  margin: 0;
  color: #ff8497;
  font-size: 13px;
}

.submit {
  padding: 11px 18px;
  background: linear-gradient(115deg, #06c7f3, #078de4);
  border: 1px solid #139de5;
  border-radius: 6px;
  color: #02141f;
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
