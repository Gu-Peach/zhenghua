import { Navigate, createBrowserRouter } from "react-router-dom";
import { AppLayout } from "@/layout/AppLayout";
import { LoginView } from "@/views/LoginView";
import { NotFoundView } from "@/views/NotFoundView";
import { ProjectView } from "@/views/ProjectView";
import { AgentsView } from "@/views/AgentsView";

export const router = createBrowserRouter([
  { path: "/login", element: <LoginView /> },
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/projects" replace /> },
      { path: "projects", element: <ProjectView /> },
      { path: "projects/:projectId", element: <ProjectView /> },
      { path: "agents", element: <AgentsView /> },
      { path: "agents/:agentId", element: <AgentsView /> },
    ],
  },
  { path: "*", element: <NotFoundView /> },
]);
