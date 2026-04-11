import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
    plugins: [react()],
    server: {
        proxy: {
            // Python --live-viz serves here; the React app calls /api/... in dev.
            "/api": {
                target: "http://127.0.0.1:8765",
                changeOrigin: true,
            },
        },
    },
});
