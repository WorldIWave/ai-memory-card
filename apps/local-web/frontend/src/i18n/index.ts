// Input: locales/en.json、locales/zh.json 翻译资源  |  Output: 初始化后的 i18n 实例
// Role: 配置 i18next + react-i18next，加载中英文资源并读取用户语言偏好
// Note: 默认语言从 localStorage(lmca-lang) 读取，缺省为中文；转义关闭以支持 HTML 插值
// Usage: 在 main.tsx 以副作用 import 触发；组件内通过 useTranslation() 获取 t 函数
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import en from './locales/en.json';
import zh from './locales/zh.json';

const savedLang = localStorage.getItem('lmca-lang') ?? 'zh';

i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, zh: { translation: zh } },
  lng: savedLang,
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
});

export default i18n;
