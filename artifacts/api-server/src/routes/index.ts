import { Router, type IRouter } from "express";
import healthRouter from "./health";
import processPdfsRouter from "./process-pdfs";

const router: IRouter = Router();

router.use(healthRouter);
router.use(processPdfsRouter);

export default router;
