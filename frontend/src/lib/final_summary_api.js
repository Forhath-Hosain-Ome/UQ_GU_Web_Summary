import axios from "axios";
import { attachInterceptors } from "./apiInterceptor";

const final_summary_api = attachInterceptors(
  axios.create({
    baseURL: "/final-summary/",
  })
);

export default final_summary_api;