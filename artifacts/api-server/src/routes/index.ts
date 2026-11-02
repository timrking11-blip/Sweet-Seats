import { Router, type IRouter } from "express";
import healthRouter from "./health";
import publicAssetRouter from "./public-asset";

const router: IRouter = Router();

router.use(healthRouter);
router.use(publicAssetRouter);

export default router;
