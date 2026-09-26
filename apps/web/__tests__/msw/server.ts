import { setupServer } from "msw/node";

export const API = "http://api.test/api/v1";

// Tests register their own handlers with server.use(...).
export const server = setupServer();
