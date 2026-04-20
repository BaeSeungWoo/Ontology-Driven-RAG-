import axios from "axios";

// 프론트가 백엔드(/chat/{factory_id})로 요청을 보낼 때 사용하는 공통 베이스 URL.
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
  headers: {
    "Content-Type": "application/json",
  },
});

export default api;
