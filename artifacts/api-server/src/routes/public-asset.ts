import type { File } from "@google-cloud/storage";
import { Router, type IRouter } from "express";
import type { Response } from "express";
import { ObjectStorageService } from "../lib/objectStorage";
import { logger } from "../lib/logger";

const router: IRouter = Router();
const VIDEO_FILE_NAME = "sweet-seats-final-cut-v3.mp4";
const objectStorageService = new ObjectStorageService();

router.head(
  "/storage/public-objects/sweet-seats-final-cut-v3.mp4",
  async (_req, res): Promise<void> => {
    try {
      const file = await objectStorageService.searchPublicObject(VIDEO_FILE_NAME);
      if (!file) {
        res.status(404).end();
        return;
      }

      const [metadata] = await file.getMetadata();
      const size = Number(metadata.size ?? 0);
      if (!Number.isSafeInteger(size) || size <= 0) {
        res.status(500).end();
        return;
      }

      res.status(200).set({
        "Accept-Ranges": "bytes",
        "Cache-Control": "public, max-age=3600",
        "Content-Length": String(size),
        "Content-Type": "video/mp4",
      }).end();
    } catch (error) {
      logger.error({ err: error }, "Failed to check Sweet Seats public video");
      res.status(500).end();
    }
  },
);

router.get(
  "/storage/public-objects/sweet-seats-final-cut-v3.mp4",
  async (req, res): Promise<void> => {
    try {
      const file = await objectStorageService.searchPublicObject(VIDEO_FILE_NAME);
      if (!file) {
        res.status(404).json({ error: "Public video not found" });
        return;
      }

      const [metadata] = await file.getMetadata();
      const size = Number(metadata.size ?? 0);
      if (!Number.isSafeInteger(size) || size <= 0) {
        res.status(500).json({ error: "Public video has invalid metadata" });
        return;
      }
      const contentType = "video/mp4";
      const rangeHeader = req.header("range");

      if (rangeHeader) {
        const range = parseByteRange(rangeHeader, size);
        if (!range) {
          res
            .status(416)
            .set("Content-Range", `bytes */${size}`)
            .end();
          return;
        }

        res.status(206).set({
          "Accept-Ranges": "bytes",
          "Cache-Control": "public, max-age=3600",
          "Content-Length": String(range.end - range.start + 1),
          "Content-Range": `bytes ${range.start}-${range.end}/${size}`,
          "Content-Type": contentType,
        });

        pipeObject(file.createReadStream({ start: range.start, end: range.end }), res);
        return;
      }

      res.status(200).set({
        "Accept-Ranges": "bytes",
        "Cache-Control": "public, max-age=3600",
        "Content-Length": String(size),
        "Content-Type": contentType,
      });
      pipeObject(file.createReadStream(), res);
    } catch (error) {
      logger.error({ err: error }, "Failed to stream Sweet Seats public video");
      res.status(500).json({ error: "Could not load the Sweet Seats video" });
    }
  },
);

function parseByteRange(
  header: string,
  size: number,
): { start: number; end: number } | null {
  const match = /^bytes=(\d*)-(\d*)$/.exec(header.trim());
  if (!match || !Number.isSafeInteger(size) || size <= 0) {
    return null;
  }

  const [, startText, endText] = match;
  if (!startText && !endText) {
    return null;
  }

  if (!startText) {
    const suffixLength = Number(endText);
    if (!Number.isSafeInteger(suffixLength) || suffixLength <= 0) {
      return null;
    }
    return { start: Math.max(size - suffixLength, 0), end: size - 1 };
  }

  const start = Number(startText);
  const requestedEnd = endText ? Number(endText) : size - 1;
  if (
    !Number.isSafeInteger(start) ||
    !Number.isSafeInteger(requestedEnd) ||
    start < 0 ||
    start >= size ||
    requestedEnd < start
  ) {
    return null;
  }

  return { start, end: Math.min(requestedEnd, size - 1) };
}

function pipeObject(
  stream: ReturnType<File["createReadStream"]>,
  response: Response,
): void {
  stream.on("error", (error: Error) => {
    logger.error({ err: error }, "Public video stream failed");
    if (response.headersSent) {
      response.destroy(error);
    } else {
      response.status(500).end();
    }
  });
  stream.pipe(response);
}

export default router;
