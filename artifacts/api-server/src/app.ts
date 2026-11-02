import express, { type Express } from "express";
import cors from "cors";
import pinoHttp from "pino-http";
import router from "./routes";
import { logger } from "./lib/logger";
import { discoveryProxy } from "./lib/discovery-service";

const app: Express = express();

app.use(
  pinoHttp({
    logger,
    serializers: {
      req(req) {
        return {
          id: req.id,
          method: req.method,
          url: req.url?.split("?")[0],
        };
      },
      res(res) {
        return {
          statusCode: res.statusCode,
        };
      },
    },
  }),
);
app.use(cors());
// Forward the original request stream before Express consumes JSON bodies.
app.use("/api/discovery", discoveryProxy);
app.use("/api/v1", discoveryProxy);
app.get("/api/health", discoveryProxy);
app.get("/api/openapi.json", discoveryProxy);
app.use("/api/docs", discoveryProxy);
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.use("/api", router);

export default app;
