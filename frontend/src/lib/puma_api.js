import axios from "axios";
import { attachInterceptors } from "./apiInterceptor";

const puma_api = attachInterceptors(
  axios.create({
    baseURL: "/api/",
  })
);

export default puma_api;