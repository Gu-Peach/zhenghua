import { Navigate, createBrowserRouter } from "react-router-dom";
import { AppLayout } from "@/layout/AppLayout";
import { LoginView } from "@/views/LoginView";
import { NotFoundView } from "@/views/NotFoundView";
import { ProjectView } from "@/views/ProjectView";

export const router = createBrowserRouter([
  { path: "/login", element: <LoginView /> },
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/projects/peru-tpp-1-sts" replace /> },
      { path: "projects", element: <Navigate to="/projects/peru-tpp-1-sts" replace /> },
      { path: "projects/:projectId", element: <ProjectView /> },
    ],
  },
  { path: "*", element: <NotFoundView /> },
]);
