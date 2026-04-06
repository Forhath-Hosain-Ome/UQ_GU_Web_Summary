import axios from "axios";
import { attachInterceptors } from "./apiInterceptor";

const auth_api = attachInterceptors(
  axios.create({
    baseURL: "/",
  })
);

export default auth_api;