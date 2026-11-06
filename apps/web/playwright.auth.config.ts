import { defineConfig } from '@playwright/test';
export default defineConfig({
 testDir:'./tests/auth',workers:1,fullyParallel:false,retries:0,forbidOnly:Boolean(process.env.CI),reporter:[['list']],
 use:{baseURL:'http://127.0.0.1:3111',trace:'retain-on-failure',launchOptions:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,args:['--no-sandbox','--disable-dev-shm-usage']}:{}}
});
