import axios from "axios";
import { attachInterceptors } from "./apiInterceptor";

const top_five_api = attachInterceptors(
  axios.create({
    baseURL: "/top-five/",
  })
);

export default top_five_api;