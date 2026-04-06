import axios from "axios";
import { attachInterceptors } from "./apiInterceptor";

const image_api = attachInterceptors(
  axios.create({
    baseURL: "/image/",
  })
);

export default image_api;