import { createLogger, format, transports } from "winston";
import { Config } from "./config.js";

export const log = createLogger({
  level: Config.LOG_LEVEL,
  format: format.combine(
    format.colorize(),
    format.timestamp({ format: "HH:mm:ss" }),
    format.printf(({ timestamp, level, message }) => `${timestamp} ${level}: ${message}`)
  ),
  transports: [new transports.Console()],
});
