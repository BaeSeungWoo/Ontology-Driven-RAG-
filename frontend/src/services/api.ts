import axios from "axios";

export type FactoryId = "yunam" | "yulkok" | "poongsan" | "yunam_origin";
let activeFactory: FactoryId = "yunam_origin";
export const executionHeaders = () => ({ "X-Factory-Id": activeFactory });
export const factoryHeaders = () => ({ "X-Factory-Id": activeFactory });
export const setApiFactory = (factory: FactoryId) => { activeFactory = factory; };

// 프론트가 백엔드(/chat/{factory_id})로 요청을 보낼 때 사용하는 공통 베이스 URL.
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "";


const api = axios.create({
  baseURL: API_BASE_URL,
  // timeout: 15000,
  headers: {
    "Content-Type": "application/json",
  },
});

api.interceptors.request.use(config => {
  if (!config.headers.has("X-Factory-Id")) config.headers.set("X-Factory-Id", activeFactory);
  return config;
});

export default api;
